# backend/app/evaluation/e1_ablation.py
"""
E1: feature ablation (PRD 9.1). Design and hypotheses are pre-registered in docs/EXPERIMENTS.md.

Run:  make e1   (needs `make dataset`; requires a passed leakage audit in reports/leakage_audit.json)

Variants A, A+B, A+B+C and leave-one-group-out from A+B+C. Each variant: LightGBM re-tuned by grouped CV
on train (same grid as step 7), calibrated on val, evaluated ONCE on held-out templates and the shifted
OOD set (val shown for reference), with paired case-bootstrap differences.
"""
import argparse
import json
from pathlib import Path

from app.engine.dataset_generator import DATASET_VERSION
from app.evaluation.baseline_report import HONEST_FRAMING
from app.features import FEATURES
from app.ml.baselines import (
    fit_rule_temperature,
    fit_solver_epsilon,
    load_states,
    rule_predictor,
    solver_distributions,
    solver_predictor,
)
from app.ml.data import Table, build_table
from app.ml.experiments import columns_for, fit_predict
from app.ml.metrics import evaluate, paired_difference
from app.ml.models import LGBM_GRID, tune
from app.provenance import git_commit

FAMILY = "lightgbm"
EVAL_SPLITS = ("val", "test_held_out_template", "test_ood_shifted")
GROUPS = {g: [f.name for f in FEATURES if f.group == g] for g in ("A", "B", "C", "context")}
VARIANTS = {
    "A": ["A"],
    "A+B": ["A", "B"],
    "A+B+C": ["A", "B", "C"],
    "A+B+C without A": ["B", "C"],
    "A+B+C without B": ["A", "C"],
    "A+B+C without C": ["A", "B"],  # identical inputs to A+B; kept so the leave-one-out table is complete
}
COMPARISONS = [("A+B", "A"), ("A+B+C", "A+B"), ("A+B+C", "A")]


def _restrict(table: Table, cols: list[int]) -> Table:
    return Table(states=table.states, X=table.X[:, cols], y=table.y, state_idx=table.state_idx, folds=table.folds)


def run_e1(dataset_dir: Path, audit_report: Path, n_boot: int = 2000, seed: int = 0, grid=None) -> dict:
    audit = json.loads(audit_report.read_text(encoding="utf-8"))
    if not audit.get("passed"):
        raise SystemExit("Leakage audit has not passed: test splits stay sealed (PRD 8.8).")
    grid = grid or LGBM_GRID
    states = load_states(dataset_dir / "features.csv", ["train", *EVAL_SPLITS])
    tables = {s: build_table([x for x in states if x.split == s]) for s in ("train", *EVAL_SPLITS)}
    train, val = tables["train"], tables["val"]

    preds: dict[str, dict[str, list]] = {split: {} for split in EVAL_SPLITS}
    tuning = {}
    for name, groups in VARIANTS.items():
        cols = columns_for([n for g in [*groups, "context"] for n in GROUPS[g]])
        if name == "A+B+C without C":  # same inputs as A+B: reuse instead of refitting
            for split in EVAL_SPLITS:
                preds[split][name] = preds[split]["A+B"]
            tuning[name] = tuning["A+B"]
            continue
        result = tune(_restrict(train, cols), FAMILY, grid)
        tuning[name] = {"best_params": result.best_params, "cv_log_loss": result.cv_log_loss[str(result.best_params)]}
        outs = fit_predict(train, val, [tables[s] for s in EVAL_SPLITS], FAMILY, result.best_params, cols)
        for split, dists in zip(EVAL_SPLITS, outs, strict=True):
            preds[split][name] = dists

    # References: rule and solver, calibrated on val exactly as in `make baselines`
    rule = rule_predictor(fit_rule_temperature(val.states))
    solver_raw = solver_distributions(dataset_dir / "snapshots.jsonl", EVAL_SPLITS)
    solver = solver_predictor(solver_raw, fit_solver_epsilon(val.states, solver_raw))
    for split in EVAL_SPLITS:
        preds[split]["rule"] = [rule(s) for s in tables[split].states]
        preds[split]["solver"] = [solver(s) for s in tables[split].states]

    results = {}
    for split in EVAL_SPLITS:
        st = tables[split].states
        p = preds[split]
        results[split] = {
            "cases": len({s.case_id for s in st}),
            "templates": sorted({s.template_id for s in st}),
            "metrics": {name: {m: evaluate(st, d, n_boot, seed)[m] for m in ("top1", "log_loss")} for name, d in p.items()},
            "comparisons": {
                f"{a} - {b}": {m: paired_difference(st, p[a], p[b], n_boot, seed)[m] for m in ("top1", "log_loss")}
                for a, b in [
                    *COMPARISONS,
                    *((v, "solver") for v in ("A", "A+B", "A+B+C")),
                    *((v, "rule") for v in ("A", "A+B", "A+B+C")),
                    *(("A+B+C", v) for v in ("A+B+C without A", "A+B+C without B")),
                ]
            },
        }
    return {
        "experiment": "E1 feature ablation (PRD 9.1); pre-registered in docs/EXPERIMENTS.md",
        "dataset_version": DATASET_VERSION,
        "git_commit": git_commit(),
        "family": FAMILY,
        "groups": GROUPS,
        "variants": VARIANTS,
        "tuning": tuning,
        "bootstrap": {"resamples": n_boot, "seed": seed, "unit": "case"},
        "results": results,
        "note": HONEST_FRAMING,
    }


def _f(c: dict) -> str:
    return f"{c['mean']:.3f} [{c['low']:.3f}, {c['high']:.3f}]"


def _verdict(c: dict, higher_is_better: bool = True) -> str:
    if c["low"] > 0:
        return "higher (CI excludes 0)" if higher_is_better else "worse (CI excludes 0)"
    if c["high"] < 0:
        return "lower (CI excludes 0)" if higher_is_better else "better (CI excludes 0)"
    return "no clear difference (CI includes 0)"


def to_markdown(r: dict) -> str:
    lines = ["# E1: feature ablation", "", f"> {r['note']}", "",
             f"Dataset v{r['dataset_version']}, commit `{r['git_commit']}`, {r['family']} re-tuned per variant. "
             "Top-1 (higher is better) and log loss (lower is better), 95% CIs over cases.", ""]
    for split, block in r["results"].items():
        lines += [f"## {split}: {block['cases']} cases, {len(block['templates'])} templates", "",
                  "| Variant | top-1 | log loss |", "|---|---|---|"]
        for name, m in block["metrics"].items():
            lines.append(f"| {name} | {_f(m['top1'])} | {_f(m['log_loss'])} |")
        lines += ["", "Paired differences (first minus second):", ""]
        for comp, m in block["comparisons"].items():
            lines.append(f"- {comp}: top-1 {_f(m['top1'])}, {_verdict(m['top1'])}; "
                         f"log loss {_f(m['log_loss'])}, {_verdict(m['log_loss'], higher_is_better=False)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(f"../data/generated/v{DATASET_VERSION}"))
    parser.add_argument("--audit", type=Path, default=Path("../reports/leakage_audit.json"))
    parser.add_argument("--out", type=Path, default=Path("../reports"))
    args = parser.parse_args()
    result = run_e1(args.dataset, args.audit)
    (args.out / "e1.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / "e1.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))


if __name__ == "__main__":
    main()
