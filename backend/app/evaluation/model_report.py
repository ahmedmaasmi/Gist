# backend/app/evaluation/model_report.py
"""
Train, tune and select the suspect ranker; report on VALIDATION only (PRD 8.4, 8.8).

Run:  make models   (or: cd backend && uv run python -m app.evaluation.model_report)

1. Grouped-CV tuning on the train split (folds = groups of templates) for Logistic Regression and LightGBM.
2. Refit each family's best configuration on all train states.
3. Fit the calibration temperature on val; evaluate on val against the baselines with 95% case-bootstrap CIs
   and paired differences.
4. Select the family with the best val log loss; save artefacts and a model card to ml/artifacts/<version>/.

Test splits are NOT touched here: the leakage audit (step 8) must pass before any test result is reported.

NOTE: scores on synthetic data measure recovery of the generator's logic, not real-world skill.
"""
import argparse
import hashlib
import json
from pathlib import Path

import joblib

from app.engine.dataset_generator import DATASET_VERSION
from app.evaluation.baseline_report import HONEST_FRAMING, STAGE_NAMES
from app.features import FEATURE_SPEC_VERSION
from app.ml.baselines import fit_rule_temperature, load_states, rule_predictor, uniform
from app.ml.data import MODEL_FEATURE_NAMES, build_table
from app.ml.metrics import METRICS, evaluate, paired_difference
from app.ml.models import (
    LGBM_GRID,
    LR_GRID,
    SEED,
    distributions,
    fit_temperature,
    lr_coefficients,
    make_model,
    positive_scores,
    tune,
)
from app.provenance import git_commit

ARTIFACTS_DIR = Path(__file__).resolve().parents[3] / "ml" / "artifacts"
FAMILIES = {"logistic_regression": LR_GRID, "lightgbm": LGBM_GRID}


def model_version(family: str, params: dict, dataset_checksum: str) -> str:
    key = json.dumps(
        {"family": family, "params": params, "data": dataset_checksum, "features": FEATURE_SPEC_VERSION, "seed": SEED},
        sort_keys=True,
    )
    return f"{family}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"


def train_and_report(dataset_dir: Path, artifacts_dir: Path = ARTIFACTS_DIR, n_boot: int = 2000, seed: int = 0,
                     verbose: bool = False) -> dict:
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    checksum = manifest.get("checksums", {}).get("features.csv", "unknown")
    states = load_states(dataset_dir / "features.csv", ["train", "val"])
    train = build_table([s for s in states if s.split == "train"])
    val = build_table([s for s in states if s.split == "val"])

    rule = rule_predictor(fit_rule_temperature(val.states))
    predictions = {
        "uniform": [uniform(s) for s in val.states],
        "motive_opportunity_rule": [rule(s) for s in val.states],
    }
    families: dict[str, dict] = {}
    fitted = {}
    for family, grid in FAMILIES.items():
        tuning = tune(train, family, grid, progress=print if verbose else (lambda _: None))
        model = make_model(family, tuning.best_params).fit(train.X, train.y)
        val_scores = positive_scores(model, val.X)
        temperature = fit_temperature(val, val_scores)
        predictions[family] = distributions(val, val_scores, temperature)
        fitted[family] = (model, temperature)
        families[family] = {
            "best_params": tuning.best_params,
            "cv_log_loss_best": tuning.cv_log_loss[str(tuning.best_params)],
            "cv_log_loss_all": tuning.cv_log_loss,
            "val_temperature": temperature,
            "version": model_version(family, tuning.best_params, checksum),
        }
        if family == "logistic_regression":
            families[family]["coefficients_standardised"] = lr_coefficients(model, MODEL_FEATURE_NAMES)

    val_results = {name: evaluate(val.states, preds, n_boot, seed) for name, preds in predictions.items()}
    selected = min(FAMILIES, key=lambda f: (val_results[f]["log_loss"]["mean"], f))
    vs_rule = {
        f: paired_difference(val.states, predictions[f], predictions["motive_opportunity_rule"], n_boot, seed)
        for f in FAMILIES
    }
    by_stage = {}
    for frac, label in STAGE_NAMES.items():
        idx = [i for i, s in enumerate(val.states) if abs(s.reveal_fraction - frac) < 1e-9]
        by_stage[label] = {
            name: evaluate([val.states[i] for i in idx], [preds[i] for i in idx], n_boot, seed)["top1"]
            for name, preds in predictions.items()
        }

    # Artefacts for the selected model (and the other family, for E1 and comparison)
    for family, (model, temperature) in fitted.items():
        out = artifacts_dir / families[family]["version"]
        out.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, out / "model.joblib")
        card = {
            "model_version": families[family]["version"],
            "family": family,
            "params": families[family]["best_params"],
            "temperature": temperature,
            "feature_names": MODEL_FEATURE_NAMES,
            "feature_spec_version": FEATURE_SPEC_VERSION,
            "dataset_version": manifest.get("dataset_version", DATASET_VERSION),
            "dataset_checksum_features_csv": checksum,
            "seed": SEED,
            "git_commit": git_commit(),
            "trained_on": "train split (all folds)",
            "calibrated_on": "val split",
            "selected": family == selected,
        }
        (out / "model_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (artifacts_dir / "SELECTED").write_text(families[selected]["version"] + "\n", encoding="utf-8")

    return {
        "dataset_version": manifest.get("dataset_version", DATASET_VERSION),
        "dataset_checksum_features_csv": checksum,
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "git_commit": git_commit(),
        "split_evaluated": "val",
        "val_cases": len({s.case_id for s in val.states}),
        "val_templates": sorted({s.template_id for s in val.states}),
        "train_cases": len({s.case_id for s in train.states}),
        "bootstrap": {"resamples": n_boot, "seed": seed, "unit": "case"},
        "families": families,
        "selected": selected,
        "val_results": val_results,
        "vs_rule": vs_rule,
        "top1_by_stage": by_stage,
        "note": HONEST_FRAMING + " Test splits are not evaluated until the leakage audit (step 8) passes.",
    }


def _fmt(c: dict) -> str:
    return f"{c['mean']:.3f} [{c['low']:.3f}, {c['high']:.3f}]"


def to_markdown(r: dict) -> str:
    lines = [
        "# Model results (validation only)",
        "",
        f"> {r['note']}",
        "",
        f"Dataset v{r['dataset_version']} (`{r['dataset_checksum_features_csv'][:12]}…`), feature spec "
        f"{r['feature_spec_version']}, commit `{r['git_commit']}`. Trained on {r['train_cases']} train cases; "
        f"evaluated on {r['val_cases']} val cases from {len(r['val_templates'])} templates. 95% CIs: "
        f"{r['bootstrap']['resamples']} bootstrap resamples over cases.",
        "",
        "| Method | " + " | ".join(METRICS) + " |",
        "|---|" + "---|" * len(METRICS),
    ]
    for name, cells in r["val_results"].items():
        lines.append(f"| {name} | " + " | ".join(_fmt(cells[m]) for m in METRICS) + " |")
    lines += ["", "## Against the motive + opportunity rule (paired, model minus rule)", ""]
    for fam, d in r["vs_rule"].items():
        beats = d["top1"]["low"] > 0 and d["log_loss"]["high"] < 0
        verdict = "beats the rule (both CIs exclude 0)" if beats else "does NOT clearly beat the rule"
        lines.append(f"- **{fam}**: top-1 {_fmt(d['top1'])}, log loss {_fmt(d['log_loss'])}: {verdict}.")
    lines += ["", "## Top-1 by amount of evidence", "", "| Method | " + " | ".join(r["top1_by_stage"]) + " |",
              "|---|" + "---|" * len(r["top1_by_stage"])]
    for name in r["val_results"]:
        lines.append(f"| {name} | " + " | ".join(_fmt(r["top1_by_stage"][st][name]) for st in r["top1_by_stage"]) + " |")
    lines += ["", "## Tuning (grouped CV on train, folds = groups of templates)", ""]
    for fam, info in r["families"].items():
        lines.append(f"- **{fam}**: best {info['best_params']} (CV log loss {info['cv_log_loss_best']}), "
                     f"val temperature {info['val_temperature']}, version `{info['version']}`")
    lines += ["", f"**Selected (best val log loss): {r['selected']}**", "",
              "## Logistic Regression coefficients (log-odds per standard deviation)", ""]
    coefs = r["families"]["logistic_regression"]["coefficients_standardised"]
    for name, c in sorted(coefs.items(), key=lambda kv: -abs(kv[1])):
        lines.append(f"- `{name}`: {c:+.3f}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(f"../data/generated/v{DATASET_VERSION}"))
    parser.add_argument("--out", type=Path, default=Path("../reports"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    report = train_and_report(args.dataset, verbose=args.verbose)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "models_val.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / "models_val.md").write_text(to_markdown(report), encoding="utf-8")
    print(to_markdown(report))


if __name__ == "__main__":
    main()
