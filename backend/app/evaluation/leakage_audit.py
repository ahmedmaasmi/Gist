# backend/app/evaluation/leakage_audit.py
"""
Leakage and shortcut audit (PRD 8.8), required before any test result is reported.

Run:  make audit-leakage   (needs `make dataset` and `make models`)

Checks, each with a pass criterion fixed in code before running:
  1. names            no model input has an excluded name; no row key or label is a model input
  2. shuffled labels  a model trained with RANDOM culprits must show no evidence of beating chance on val:
                      the upper 95% bound of (its top-1 minus uniform) must be <= 0.03. Scoring BELOW chance
                      is allowed: a tree fitted to random labels favours the densest (typical, innocent-looking)
                      region, so real culprits, who are outliers, end up ranked lower.
  3. single features  no single feature (with its relative twin) comes within 0.05 top-1 of the full model
  4. permutation      no single feature is so dominant that permuting it drops the model to near chance
  5. reveal/order     a) the stage-0 "briefing" fact must not name the culprit more often than a random
                         crime-scene record does (difference <= 0.10)
                      b) features recomputed from the visible snapshot alone match the dataset exactly
                      c) reversing the order suspects are listed in changes no probability
Everything uses train (fit) and val (measure). Test splits are not touched.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from app.engine.dataset_generator import DATASET_VERSION, FEATURE_TABLE_KEYS
from app.evaluation.baseline_report import HONEST_FRAMING
from app.features import compute_suspect_features
from app.features.spec import EXCLUDED_NAME_TOKENS
from app.ml.baselines import FEATURE_NAMES, load_states, uniform
from app.ml.data import MODEL_FEATURE_NAMES, build_table, matrix_from_features
from app.ml.experiments import columns_for, fit_predict
from app.ml.metrics import evaluate, paired_difference
from app.ml.models import distributions, fit_temperature, make_model, positive_scores
from app.provenance import git_commit

SHUFFLED_MAX_GAIN = 0.03
NEAR_SHORTCUT_MARGIN = 0.05
DOMINANCE_MARGIN = 0.05
BRIEFING_TOLERANCE = 0.10


def name_violations(model_inputs: list[str]) -> tuple[list[str], list[str]]:
    """(inputs whose name has an excluded token, row keys/labels used as inputs). Both must be empty."""
    bad = [n for n in model_inputs if set(n.removesuffix("_rel").split("_")) & EXCLUDED_NAME_TOKENS]
    return bad, sorted(set(model_inputs) & set(FEATURE_TABLE_KEYS))


def _check(passed: bool, **details) -> dict:
    return {"passed": bool(passed), **details}


def run_audit(dataset_dir: Path, models_report: Path, n_boot: int = 1000, seed: int = 0) -> dict:
    report = json.loads(models_report.read_text(encoding="utf-8"))
    family = report["selected"]
    params = report["families"][family]["best_params"]
    states = load_states(dataset_dir / "features.csv", ["train", "val"])
    train = build_table([s for s in states if s.split == "train"])
    val = build_table([s for s in states if s.split == "val"])
    all_cols = list(range(len(MODEL_FEATURE_NAMES)))
    uniform_val = [uniform(s) for s in val.states]
    rng = np.random.default_rng(seed)
    checks: dict[str, dict] = {}

    # 1. Names
    bad, overlap = name_violations(MODEL_FEATURE_NAMES)
    checks["names"] = _check(not bad and not overlap, excluded_names=bad, keys_used_as_inputs=overlap)

    # Full model on val (reference)
    full = fit_predict(train, val, [val], family, params, all_cols)[0]
    full_eval = evaluate(val.states, full, n_boot, seed)
    full_top1 = full_eval["top1"]["mean"]

    # 2. Shuffled-label control: give every train state a random culprit
    y_shuffled = np.zeros_like(train.y)
    for i in range(len(train.states)):
        rows = np.flatnonzero(train.state_idx == i)
        y_shuffled[rng.choice(rows)] = 1
    shuffled = fit_predict(train, val, [val], family, params, all_cols, y_train=y_shuffled)[0]
    diff = paired_difference(val.states, shuffled, uniform_val, n_boot, seed)
    checks["shuffled_labels"] = _check(
        diff["top1"]["high"] <= SHUFFLED_MAX_GAIN,
        val_top1=evaluate(val.states, shuffled, n_boot, seed)["top1"],
        top1_minus_uniform=diff["top1"],
    )

    # 3. Single-feature models
    singles = {}
    for name in FEATURE_NAMES:
        preds = fit_predict(train, val, [val], family, params, columns_for([name]))[0]
        singles[name] = evaluate(val.states, preds, n_boot, seed)["top1"]
    near = [n for n, c in singles.items() if c["mean"] >= full_top1 - NEAR_SHORTCUT_MARGIN]
    checks["single_features"] = _check(not near, full_model_top1=full_top1, top1_by_feature=singles,
                                       near_shortcuts=near)

    # 4. Permutation importance (selected model, val): shuffle one feature (and its twin) across val rows
    model = make_model(family, params).fit(train.X, train.y)
    temperature = fit_temperature(val, positive_scores(model, val.X))
    base_dists = distributions(val, positive_scores(model, val.X), temperature)
    base_top1 = evaluate(val.states, base_dists, 100, seed)["top1"]["mean"]
    chance = float(np.mean([1 / len(s.suspect_ids) for s in val.states]))
    importance = {}
    for name in FEATURE_NAMES:
        X = val.X.copy()
        perm = rng.permutation(len(X))
        for c in columns_for([name]):
            X[:, c] = X[perm, c]
        d = distributions(val, positive_scores(model, X), temperature)
        importance[name] = round(base_top1 - evaluate(val.states, d, 100, seed)["top1"]["mean"], 4)
    dominant = [n for n, drop in importance.items() if base_top1 - drop <= chance + DOMINANCE_MARGIN]
    checks["permutation_importance"] = _check(
        not dominant, top1=base_top1, chance=round(chance, 4),
        top1_drop_when_permuted=dict(sorted(importance.items(), key=lambda kv: -kv[1])), dominant=dominant,
    )

    # 5. Reveal artefacts and order
    briefing_hits = briefing_n = scene_hits = scene_n = 0
    recomputed = mismatches = 0
    order_checked = order_changed = 0
    val_by_key = {s.key: s for s in val.states}
    with (dataset_dir / "snapshots.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if '"split": "train"' not in line and '"split": "val"' not in line:
                continue
            snap = json.loads(line)
            facts = snap["t1_partial"]["discovered_facts"]
            if snap["split"] == "train" and snap["stage_idx"] == 0 and facts:
                briefing_n += 1
                briefing_hits += facts[0]["subject_id"] == snap["culprit_id"]
            if snap["split"] == "train" and snap["reveal_fraction"] == 1.0:
                scene = [x for x in facts if x["location_id"] == snap["crime_location_id"] and x["subject_id"]]
                scene_n += len(scene)
                scene_hits += sum(x["subject_id"] == snap["culprit_id"] for x in scene)
            key = (snap["case_id"], snap["order_idx"], snap["stage_idx"])
            if snap["split"] == "val" and key in val_by_key and recomputed < 200:
                from app.domain.setting import SettingTemplate
                from app.domain.tiers import T0Public, T1Session

                t0 = T0Public.model_validate(snap["t0_public"])
                rows = compute_suspect_features(
                    t0, T1Session.model_validate(snap["t1_partial"]), SettingTemplate.model_validate(snap["setting"])
                )
                recomputed += 1
                state = val_by_key[key]
                mismatches += any(
                    abs(r.features[n] - state.features[r.suspect_id][n]) > 1e-6
                    for r in rows for n in FEATURE_NAMES
                )
                if order_checked < 100:
                    fwd = model.predict_proba(matrix_from_features(state.suspect_ids, state.features))[:, 1]
                    rev = model.predict_proba(matrix_from_features(state.suspect_ids[::-1], state.features))[:, 1]
                    order_checked += 1
                    order_changed += not np.allclose(fwd, rev[::-1])
    briefing_rate = briefing_hits / max(briefing_n, 1)
    scene_rate = scene_hits / max(scene_n, 1)
    checks["briefing_fact"] = _check(
        briefing_rate - scene_rate <= BRIEFING_TOLERANCE,
        briefing_names_culprit=round(briefing_rate, 4), random_scene_record_names_culprit=round(scene_rate, 4),
        stage0_states=briefing_n,
    )
    checks["features_from_visible_state_only"] = _check(mismatches == 0, states_recomputed=recomputed,
                                                       mismatches=mismatches)
    checks["suspect_order_invariance"] = _check(order_changed == 0, states_checked=order_checked,
                                               changed=order_changed)

    return {
        "dataset_version": DATASET_VERSION,
        "git_commit": git_commit(),
        "model_family": family,
        "model_params": params,
        "full_model_val": full_eval,
        "checks": checks,
        "passed": all(c["passed"] for c in checks.values()),
        "note": HONEST_FRAMING,
    }


def to_markdown(r: dict) -> str:
    c = r["checks"]
    mark = {True: "PASS", False: "FAIL"}
    lines = [
        f"# Leakage and shortcut audit: {'PASSED' if r['passed'] else 'FAILED'}",
        "",
        f"> {r['note']}",
        "",
        f"Dataset v{r['dataset_version']}, commit `{r['git_commit']}`, model {r['model_family']} {r['model_params']}. "
        "Fit on train, measured on val; test splits untouched.",
        "",
        "| Check | Result | Key numbers |",
        "|---|---|---|",
        f"| 1. Feature names | {mark[c['names']['passed']]} | excluded names: {c['names']['excluded_names'] or 'none'}; "
        f"keys used as inputs: {c['names']['keys_used_as_inputs'] or 'none'} |",
        f"| 2. Shuffled labels | {mark[c['shuffled_labels']['passed']]} | val top-1 with random culprits "
        f"{c['shuffled_labels']['val_top1']['mean']:.3f}; minus uniform {c['shuffled_labels']['top1_minus_uniform']['mean']:+.3f} "
        f"[{c['shuffled_labels']['top1_minus_uniform']['low']:+.3f}, {c['shuffled_labels']['top1_minus_uniform']['high']:+.3f}] |",
        f"| 3. Single-feature models | {mark[c['single_features']['passed']]} | full model {c['single_features']['full_model_top1']:.3f}; "
        f"near-shortcuts: {c['single_features']['near_shortcuts'] or 'none'} |",
        f"| 4. Permutation importance | {mark[c['permutation_importance']['passed']]} | dominant features: "
        f"{c['permutation_importance']['dominant'] or 'none'} (chance {c['permutation_importance']['chance']}) |",
        f"| 5a. Stage-0 briefing fact | {mark[c['briefing_fact']['passed']]} | names culprit "
        f"{c['briefing_fact']['briefing_names_culprit']:.3f} vs random scene record "
        f"{c['briefing_fact']['random_scene_record_names_culprit']:.3f} |",
        f"| 5b. Features from visible state only | {mark[c['features_from_visible_state_only']['passed']]} | "
        f"{c['features_from_visible_state_only']['mismatches']} mismatches in "
        f"{c['features_from_visible_state_only']['states_recomputed']} recomputed states |",
        f"| 5c. Suspect-order invariance | {mark[c['suspect_order_invariance']['passed']]} | "
        f"{c['suspect_order_invariance']['changed']} of {c['suspect_order_invariance']['states_checked']} changed |",
        "",
        "## Single-feature models (val top-1)",
        "",
        *(f"- `{n}`: {v['mean']:.3f} [{v['low']:.3f}, {v['high']:.3f}]"
          for n, v in sorted(c["single_features"]["top1_by_feature"].items(), key=lambda kv: -kv[1]["mean"])),
        "",
        "## Permutation importance (drop in val top-1 when the feature is shuffled)",
        "",
        *(f"- `{n}`: {d:+.3f}" for n, d in c["permutation_importance"]["top1_drop_when_permuted"].items()),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(f"../data/generated/v{DATASET_VERSION}"))
    parser.add_argument("--models-report", type=Path, default=Path("../reports/models_val.json"))
    parser.add_argument("--out", type=Path, default=Path("../reports"))
    args = parser.parse_args()
    result = run_audit(args.dataset, args.models_report)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "leakage_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / "leakage_audit.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))


if __name__ == "__main__":
    main()
