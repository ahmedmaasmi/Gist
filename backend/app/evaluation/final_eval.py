# backend/app/evaluation/final_eval.py
"""
One-time test evaluation of the selected model (PRD 8.4: "test sets are evaluated once per final model").

Run:  make final-eval   (requires a PASSED leakage audit)

Uses the deployed path: the saved artefact via `Ranker.load()` and `Ranker.rank(t0, t1, setting)` on every
test evidence state, so what is measured is exactly what the game will run. Compared with the rule and the
solver using paired case-bootstrap differences; abstention coverage and accuracy are reported per split.
"""
import argparse
import json
from pathlib import Path

from app.domain.setting import SettingTemplate
from app.domain.tiers import T0Public, T1Session
from app.engine.dataset_generator import DATASET_VERSION
from app.evaluation.baseline_report import HONEST_FRAMING, stage_indices
from app.evaluation.contradiction_audit import wilson
from app.ml.baselines import (
    fit_rule_temperature,
    fit_solver_epsilon,
    load_states,
    rule_predictor,
    solver_distributions,
    solver_predictor,
    uniform,
)
from app.ml.metrics import METRICS, evaluate, paired_difference
from app.ml.ranker import Ranker
from app.provenance import git_commit

TEST_SPLITS = ("test_in_dist", "test_held_out_template", "test_ood_shifted")


def run_final(dataset_dir: Path, audit_report: Path, n_boot: int = 2000, seed: int = 0, ranker: Ranker | None = None) -> dict:
    if not json.loads(audit_report.read_text(encoding="utf-8")).get("passed"):
        raise SystemExit("Leakage audit has not passed: test splits stay sealed (PRD 8.8).")
    ranker = ranker or Ranker.load()
    if ranker.fallback:
        raise SystemExit("No trained model artefact found: run `make models` first.")

    states = load_states(dataset_dir / "features.csv", ["val", *TEST_SPLITS])
    by_key = {s.key: s for s in states}
    ranked: dict[tuple, dict] = {}
    with (dataset_dir / "snapshots.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if not any(f'"split": "{s}"' in line for s in TEST_SPLITS):
                continue
            snap = json.loads(line)
            key = (snap["case_id"], snap["order_idx"], snap["stage_idx"])
            result = ranker.rank(
                T0Public.model_validate(snap["t0_public"]),
                T1Session.model_validate(snap["t1_partial"]),
                SettingTemplate.model_validate(snap["setting"]),
            )
            ranked[key] = {"probs": result.probabilities, "abstain": result.abstain, "leader": result.leading_suspect_id}

    val_states = [s for s in states if s.split == "val"]
    rule = rule_predictor(fit_rule_temperature(val_states))
    solver_raw = solver_distributions(dataset_dir / "snapshots.jsonl", TEST_SPLITS)
    solver = solver_predictor(solver_raw, fit_solver_epsilon(val_states, solver_distributions(
        dataset_dir / "snapshots.jsonl", ["val"])))

    results = {}
    for split in TEST_SPLITS:
        st = [s for s in states if s.split == split]
        preds = {
            "model": [ranked[s.key]["probs"] for s in st],
            "motive_opportunity_rule": [rule(s) for s in st],
            "timeline_solver": [solver(s) for s in st],
            "uniform": [uniform(s) for s in st],
        }
        answered = [s for s in st if not ranked[s.key]["abstain"]]
        correct = sum(ranked[s.key]["leader"] == s.culprit_id for s in answered)
        stages = {}
        for label, idx in stage_indices(st).items():
            stages[label] = {n: evaluate([st[i] for i in idx], [p[i] for i in idx], n_boot, seed)["top1"]
                             for n, p in preds.items()}
        results[split] = {
            "cases": len({s.case_id for s in st}),
            "templates": sorted({s.template_id for s in st}),
            "metrics": {n: evaluate(st, p, n_boot, seed) for n, p in preds.items()},
            "model_minus": {
                ref: {m: paired_difference(st, preds["model"], preds[ref], n_boot, seed)[m] for m in ("top1", "log_loss")}
                for ref in ("motive_opportunity_rule", "timeline_solver", "uniform")
            },
            "top1_by_stage": stages,
            "abstention": {
                "coverage": wilson(len(answered), len(st)),
                "accuracy_when_answering": wilson(correct, len(answered)),
            },
        }
    assert all(k in by_key for k in ranked)
    return {
        "evaluation": "one-time test evaluation of the selected model (PRD 8.4)",
        "model_version": ranker.card["model_version"],
        "abstention_thresholds": ranker.card["abstention"],
        "dataset_version": DATASET_VERSION,
        "git_commit": git_commit(),
        "bootstrap": {"resamples": n_boot, "seed": seed, "unit": "case"},
        "results": results,
        "note": HONEST_FRAMING,
    }


def _f(c: dict) -> str:
    return f"{c['mean']:.3f} [{c['low']:.3f}, {c['high']:.3f}]"


def to_markdown(r: dict) -> str:
    lines = ["# Final test evaluation (run once)", "", f"> {r['note']}", "",
             f"Model `{r['model_version']}` (selected on val in step 7), dataset v{r['dataset_version']}, "
             f"commit `{r['git_commit']}`. Leakage audit passed beforehand. 95% CIs over cases "
             f"({r['bootstrap']['resamples']} resamples); abstention proportions with Wilson intervals.", ""]
    for split, b in r["results"].items():
        lines += [f"## {split}: {b['cases']} cases, {len(b['templates'])} templates", "",
                  "| Method | " + " | ".join(METRICS) + " |", "|---|" + "---|" * len(METRICS)]
        for name, cells in b["metrics"].items():
            lines.append(f"| {name} | " + " | ".join(_f(cells[m]) for m in METRICS) + " |")
        lines += ["", "Model minus reference (paired):", ""]
        for ref, d in b["model_minus"].items():
            beats = d["top1"]["low"] > 0 and d["log_loss"]["high"] < 0
            lines.append(f"- vs {ref}: top-1 {_f(d['top1'])}, log loss {_f(d['log_loss'])}: "
                         f"{'beats it (both CIs exclude 0)' if beats else 'does NOT clearly beat it'}")
        cov, acc = b["abstention"]["coverage"], b["abstention"]["accuracy_when_answering"]
        lines += ["", f"Abstention: names a suspect in {cov[0]:.1%} [{cov[1]:.1%}, {cov[2]:.1%}] of evidence states, "
                  f"correct {acc[0]:.1%} [{acc[1]:.1%}, {acc[2]:.1%}] of the time when it does "
                  f"(target set on val: {r['abstention_thresholds']['target_accuracy']:.0%}).", "",
                  "Model top-1 by evidence revealed: " + ", ".join(
                      f"{st} {_f(v['model'])}" for st, v in b["top1_by_stage"].items()), ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(f"../data/generated/v{DATASET_VERSION}"))
    parser.add_argument("--audit", type=Path, default=Path("../reports/leakage_audit.json"))
    parser.add_argument("--out", type=Path, default=Path("../reports"))
    args = parser.parse_args()
    result = run_final(args.dataset, args.audit)
    (args.out / "final_test.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / "final_test.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))


if __name__ == "__main__":
    main()
