# backend/app/evaluation/e3_policies.py
"""
E3: question policies (PRD 9.3). Design and hypotheses are pre-registered in docs/EXPERIMENTS.md.

Run:  make e3   (needs `make models`)

1. Estimate the answer-outcome model on fresh cases from DEV templates (mixed population).
2. Run every policy x population on the same fresh cases from HELD-OUT templates, budget 8, and report
   top-1 after 3/5/8 actions and actions-to-reach-and-hold, with paired case-bootstrap CIs.
"""
import argparse
import json
import random
from pathlib import Path

import numpy as np

from app.engine.dataset_generator import DatasetGenerator
from app.engine.templates import CASE_VARIABLE_RANGES, load_all_templates
from app.evaluation.baseline_report import HONEST_FRAMING
from app.ml.ranker import Ranker
from app.modes.mode1_detective.episode import OUTCOMES, apply_action, initial_state, run_episode
from app.modes.mode1_detective.players import POPULATIONS, behaviours
from app.modes.mode1_detective.policies import (
    EntropyPolicy,
    FixedOrderPolicy,
    OutcomeModel,
    RandomPolicy,
    TopTwoPolicy,
)
from app.modes.mode1_detective.questions import build_question_bank
from app.provenance import git_commit

BUDGETS = (3, 5, 8)
MAX_BUDGET = 8
OUTCOME_SEED, EVAL_SEED = 5_000_000, 6_000_000


def make_cases(group: str, n: int, base_seed: int) -> list:
    templates = [t for t in (load_all_templates()[k] for k in sorted(load_all_templates())) if t.split_group == group]
    cases = []
    for i in range(n):
        tpl = templates[i % len(templates)]
        bundle, _ = DatasetGenerator._generate_validated_case(
            tpl, f"case_e3_{tpl.template_id}_{i:04d}", base_seed + i * 100, CASE_VARIABLE_RANGES
        )
        cases.append(bundle)
    return cases


def estimate_outcome_model(cases, start_fraction: float) -> OutcomeModel:
    counts = {k: {r: dict.fromkeys(OUTCOMES[k], 0) for r in ("culprit", "innocent")} for k in OUTCOMES}
    for i, bundle in enumerate(cases):
        t1, who, rng = initial_state(bundle, start_fraction), behaviours(bundle, "mixed"), random.Random(i)
        for action in build_question_bank(bundle.t0_public):
            _, outcome = apply_action(bundle, t1, action, who, rng, 1)
            role = "culprit" if action.suspect_id == bundle.t3_canonical.culprit_id else "innocent"
            counts[action.kind][role][outcome] += 1
    return OutcomeModel(counts)


def _ci(values: np.ndarray, n_boot: int, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    boot = values[rng.integers(0, len(values), size=(n_boot, len(values)))].mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"mean": round(float(values.mean()), 4), "low": round(float(lo), 4), "high": round(float(hi), 4)}


def run_e3(n_cases: int = 300, start_fraction: float | None = None, n_boot: int = 2000, seed: int = 0,
           ranker: Ranker | None = None) -> dict:
    from app.modes.mode1_detective.episode import START_FRACTION

    start = START_FRACTION if start_fraction is None else start_fraction
    ranker = ranker or Ranker.load()
    model = estimate_outcome_model(make_cases("dev", n_cases, OUTCOME_SEED), start)
    cases = make_cases("test_held_out_template", n_cases, EVAL_SEED)
    policies = [RandomPolicy(), FixedOrderPolicy(), TopTwoPolicy(), EntropyPolicy(model)]

    results: dict = {}
    for population in POPULATIONS:
        per_policy = {}
        for policy in policies:
            eps = [run_episode(b, policy, population, ranker, MAX_BUDGET, seed=i, start_fraction=start)
                   for i, b in enumerate(cases)]
            correct = np.array([e.correct_by_step for e in eps], dtype=float)  # (cases, budget+1)
            per_policy[policy.name] = {
                "correct": correct,
                "reach_hold": np.array([e.reach_and_hold for e in eps], dtype=float),
                "example": {"actions": eps[0].actions, "outcomes": eps[0].outcomes,
                            "first_decision": eps[0].decision_logs[0]},
            }
        block = {"policies": {}, "entropy_minus": {}}
        for name, d in per_policy.items():
            block["policies"][name] = {
                **{f"top1_after_{k}": _ci(d["correct"][:, k], n_boot, seed) for k in (0, *BUDGETS)},
                "actions_to_reach_and_hold": _ci(d["reach_hold"], n_boot, seed),
                "reached_within_budget": round(float((d["reach_hold"] <= MAX_BUDGET).mean()), 4),
                "example_episode": d["example"],
            }
        ent = per_policy["entropy"]
        for name, d in per_policy.items():
            if name == "entropy":
                continue
            block["entropy_minus"][name] = {
                **{f"top1_after_{k}": _ci(ent["correct"][:, k] - d["correct"][:, k], n_boot, seed) for k in BUDGETS},
                "actions_to_reach_and_hold": _ci(ent["reach_hold"] - d["reach_hold"], n_boot, seed),
            }
        results[population] = block
    return {
        "experiment": "E3 question policies (PRD 9.3); pre-registered in docs/EXPERIMENTS.md",
        "git_commit": git_commit(),
        "model_version": ranker.card.get("model_version", "rule-fallback"),
        "start_fraction": start,
        "cases": n_cases,
        "templates": "test_held_out_template (train, lodge, abbey)",
        "outcome_model": model.counts,
        "results": results,
        "note": HONEST_FRAMING,
    }


def _f(c: dict) -> str:
    return f"{c['mean']:.3f} [{c['low']:.3f}, {c['high']:.3f}]"


def to_markdown(r: dict) -> str:
    lines = ["# E3: question policies", "", f"> {r['note']}", "",
             f"{r['cases']} fresh cases on {r['templates']}, start at {r['start_fraction']:.0%} of the evidence, "
             f"ranker `{r['model_version']}`, commit `{r['git_commit']}`. Top-1 = the leading suspect is the "
             "culprit. 95% CIs over cases; differences are paired (same cases).", ""]
    for pop, block in r["results"].items():
        lines += [f"## {pop}", "", "| Policy | start | after 3 | after 5 | after 8 | actions to reach & hold |",
                  "|---|---|---|---|---|---|"]
        for name, m in block["policies"].items():
            lines.append(f"| {name} | {m['top1_after_0']['mean']:.3f} | {_f(m['top1_after_3'])} | {_f(m['top1_after_5'])} | "
                         f"{_f(m['top1_after_8'])} | {_f(m['actions_to_reach_and_hold'])} |")
        lines += ["", "Entropy minus other policy (top-1: positive = entropy better; actions: negative = entropy faster):", ""]
        for name, d in block["entropy_minus"].items():
            lines.append(f"- vs {name}: after 3 {_f(d['top1_after_3'])}, after 5 {_f(d['top1_after_5'])}, "
                         f"after 8 {_f(d['top1_after_8'])}; actions {_f(d['actions_to_reach_and_hold'])}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=300)
    parser.add_argument("--start", type=float, default=None, help="starting evidence fraction (default 0.15)")
    parser.add_argument("--out", type=Path, default=Path("../reports"))
    args = parser.parse_args()
    result = run_e3(args.cases, args.start)
    suffix = "" if args.start is None else f"_start{int(args.start * 100)}"
    (args.out / f"e3{suffix}.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / f"e3{suffix}.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))


if __name__ == "__main__":
    main()
