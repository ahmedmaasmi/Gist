# backend/app/evaluation/baseline_report.py
"""
Baseline table with confidence intervals (PRD 8.5, 8.6; v0.1 exit gate).

Run:  make baselines   (or: cd backend && uv run python -m app.evaluation.baseline_report)

Reads a dataset built by `make dataset`, fits each baseline's single calibration knob on the VAL split,
then evaluates every baseline on val and on the test splits with 95% bootstrap CIs over cases.

NOTE: scores on synthetic data measure recovery of the generator's logic, not real-world skill.
"""
import argparse
import json
from pathlib import Path

from app.engine.dataset_generator import DATASET_VERSION
from app.ml.baselines import (
    RULE_LOG_ACCESS_WEIGHT,
    RULE_WEIGHTS,
    fit_rule_temperature,
    fit_solver_epsilon,
    load_states,
    rule_predictor,
    solver_distributions,
    solver_predictor,
    uniform,
)
from app.ml.metrics import METRICS, evaluate, paired_difference
from app.provenance import git_commit

EVAL_SPLITS = ("val", "test_in_dist", "test_held_out_template", "test_ood_shifted")
STAGE_NAMES = {0.35: "35% of evidence", 0.65: "65% of evidence", 1.0: "all evidence"}
HONEST_FRAMING = (
    "Scores on synthetic cases measure how well a method recovers the case generator's logic. "
    "They are not evidence of real-world investigative ability. Generalisation claims rest only on the "
    "held-out templates and the shifted OOD set (no hand-authored cases, D-020)."
)




def build_report(dataset_dir: Path, n_boot: int = 2000, seed: int = 0) -> dict:
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    states = load_states(dataset_dir / "features.csv", EVAL_SPLITS)
    solver_raw = solver_distributions(dataset_dir / "snapshots.jsonl", EVAL_SPLITS)

    val_states = [s for s in states if s.split == "val"]
    temperature = fit_rule_temperature(val_states)
    epsilon = fit_solver_epsilon(val_states, solver_raw)
    predictors = {
        "uniform": uniform,
        "motive_opportunity_rule": rule_predictor(temperature),
        "timeline_solver": solver_predictor(solver_raw, epsilon),
    }

    results: dict[str, dict] = {}
    for split in EVAL_SPLITS:
        split_states = [s for s in states if s.split == split]
        preds = {name: [p(s) for s in split_states] for name, p in predictors.items()}
        block: dict = {
            "cases": len({s.case_id for s in split_states}),
            "templates": sorted({s.template_id for s in split_states}),
            "evidence_states": len(split_states),
            "overall": {name: evaluate(split_states, preds[name], n_boot, seed) for name in predictors},
            "vs_uniform": {
                name: paired_difference(split_states, preds[name], preds["uniform"], n_boot, seed)
                for name in predictors
                if name != "uniform"
            },
            "by_stage": {},
        }
        for frac, label in STAGE_NAMES.items():
            idx = [i for i, s in enumerate(split_states) if abs(s.reveal_fraction - frac) < 1e-9]
            stage_states = [split_states[i] for i in idx]
            block["by_stage"][label] = {
                name: evaluate(stage_states, [preds[name][i] for i in idx], n_boot, seed) for name in predictors
            }
        results[split] = block

    return {
        "dataset_version": manifest.get("dataset_version", DATASET_VERSION),
        "dataset_checksum_features_csv": manifest.get("checksums", {}).get("features.csv"),
        "feature_spec_version": manifest.get("feature_spec_version"),
        "git_commit": git_commit(),
        "bootstrap": {"resamples": n_boot, "seed": seed, "unit": "case", "interval": "95% percentile"},
        "fitted_on_val": {"rule_softmax_temperature": temperature, "solver_uniform_epsilon": epsilon},
        "rule_definition": {"weights": RULE_WEIGHTS, "log1p_access_evidence_weight": RULE_LOG_ACCESS_WEIGHT},
        "note": HONEST_FRAMING,
        "results": results,
    }


def _fmt(cell: dict[str, float]) -> str:
    return f"{cell['mean']:.3f} [{cell['low']:.3f}, {cell['high']:.3f}]"


def to_markdown(report: dict) -> str:
    lines = [
        "# Baseline results",
        "",
        f"> {report['note']}",
        "",
        f"Dataset v{report['dataset_version']} (features.csv sha256 `{str(report['dataset_checksum_features_csv'])[:12]}…`), "
        f"feature spec {report['feature_spec_version']}, commit `{report['git_commit']}`. "
        f"95% CIs from {report['bootstrap']['resamples']} bootstrap resamples over cases (seed {report['bootstrap']['seed']}). "
        f"Calibration fitted on val: rule temperature {report['fitted_on_val']['rule_softmax_temperature']}, "
        f"solver epsilon {report['fitted_on_val']['solver_uniform_epsilon']}.",
        "",
        "Higher is better for top-1, top-2 and MRR; lower is better for log loss and Brier.",
    ]
    for split, block in report["results"].items():
        lines += [
            "",
            f"## {split}: {block['cases']} cases, {len(block['templates'])} templates, {block['evidence_states']} evidence states",
            "",
            "| Baseline | " + " | ".join(METRICS) + " |",
            "|---|" + "---|" * len(METRICS),
        ]
        for name, cells in block["overall"].items():
            lines.append(f"| {name} | " + " | ".join(_fmt(cells[m]) for m in METRICS) + " |")
        lines += ["", "Difference vs uniform (paired; CI excluding 0 = real difference):", ""]
        for name, cells in block["vs_uniform"].items():
            lines.append(f"- {name}: top-1 {_fmt(cells['top1'])}, log loss {_fmt(cells['log_loss'])}")
        lines += ["", "Top-1 by amount of evidence revealed:", "", "| Baseline | " + " | ".join(block["by_stage"]) + " |",
                  "|---|" + "---|" * len(block["by_stage"])]
        for name in block["overall"]:
            lines.append(
                f"| {name} | " + " | ".join(_fmt(block["by_stage"][st][name]["top1"]) for st in block["by_stage"]) + " |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(f"../data/generated/v{DATASET_VERSION}"))
    parser.add_argument("--out", type=Path, default=Path("../reports"))
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    report = build_report(args.dataset, args.resamples, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "baselines.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / "baselines.md").write_text(to_markdown(report), encoding="utf-8")
    print(to_markdown(report))


if __name__ == "__main__":
    main()
