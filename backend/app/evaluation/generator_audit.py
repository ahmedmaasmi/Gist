# backend/app/evaluation/generator_audit.py
"""
Generator shortcut audit (PRD 8.2, 8.8): how much of the label can trivial rules recover?

Run:  make audit-generator   (or: cd backend && uv run python -m app.evaluation.generator_audit)

Each rule ranks suspects by one hand-picked signal computed from the *full* discoverable T1
evidence (best case for the rule). Ties are split fairly: if k suspects share the top score
and the culprit is among them, the rule scores 1/k. Chance level is 1 / number of suspects.

NOTE: scores on synthetic data measure recovery of the generator's logic, not real-world skill.
"""
import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from statistics import mean

from app.domain.enums import EvidenceCategory, LieKind
from app.domain.simulation import SimulatedCaseBundle
from app.engine.solver import CaseSolvabilityValidator
from app.engine.templates import get_template, load_all_templates, sample_case_setup_from_template

Rule = Callable[[SimulatedCaseBundle], dict[str, float]]


def _in_scene_window(bundle: SimulatedCaseBundle, fact) -> bool:
    t0 = bundle.t0_public
    return (
        fact.location_id == t0.crime_location_id
        and fact.time_interval is not None
        and t0.crime_window is not None
        and fact.time_interval.overlaps(t0.crime_window)
    )


def rule_motive(bundle: SimulatedCaseBundle) -> dict[str, float]:
    scores = dict.fromkeys(bundle.t0_public.suspect_ids, 0.0)
    for f in bundle.t1_session.discovered_facts:
        if f.category == EvidenceCategory.MOTIVE and f.subject_id in scores:
            scores[f.subject_id] += f.reliability
    return scores


def rule_scene_presence(bundle: SimulatedCaseBundle) -> dict[str, float]:
    scores = dict.fromkeys(bundle.t0_public.suspect_ids, 0.0)
    for f in bundle.t1_session.discovered_facts:
        if f.subject_id in scores and _in_scene_window(bundle, f):
            scores[f.subject_id] += f.reliability
    return scores


def rule_has_forensic(bundle: SimulatedCaseBundle) -> dict[str, float]:
    scores = dict.fromkeys(bundle.t0_public.suspect_ids, 0.0)
    for f in bundle.t1_session.discovered_facts:
        if f.category == EvidenceCategory.FORENSIC and f.subject_id in scores:
            scores[f.subject_id] = 1.0
    return scores


def rule_validator_support(bundle: SimulatedCaseBundle, setting) -> dict[str, float]:
    contradictions = CaseSolvabilityValidator._collect_all_contradictions(bundle.t1_session, setting)
    return CaseSolvabilityValidator._compute_discoverable_support_scores(
        suspect_ids=bundle.t0_public.suspect_ids,
        t1=bundle.t1_session,
        contradictions=contradictions,
        crime_location_id=bundle.t0_public.crime_location_id,
        murder_window=bundle.t0_public.crime_window,
    )


def top1_credit(scores: dict[str, float], culprit: str) -> float:
    best = max(scores.values())
    top = [s for s, v in scores.items() if abs(v - best) < 1e-9]
    return 1.0 / len(top) if culprit in top else 0.0


def run(seeds: int = 50, num_suspects: int = 4) -> dict:
    credits: dict[str, list[float]] = {}
    counts: Counter = Counter()
    selection_probs: list[float] = []
    for template_id in sorted(load_all_templates()):
        tpl = get_template(template_id)
        for seed in range(seeds):
            bundle = sample_case_setup_from_template(template=tpl, seed=seed, num_suspects=num_suspects).simulate()
            t3 = bundle.t3_canonical
            report = CaseSolvabilityValidator.validate_case(bundle=bundle, setting=tpl, allow_hard_cases=True)
            counts["cases"] += 1
            counts["checks_1_to_3_pass"] += report.is_valid
            counts[f"difficulty={report.difficulty_estimate}"] += 1
            lies = Counter(a.kind for a in t3.lie_annotations)
            counts["culprit_lied"] += lies[LieKind.CULPRIT_COVER_STORY] > 0
            counts[f"cover_for_lies={lies[LieKind.COVER_FOR]}"] += 1
            counts["red_herring_lies"] += lies[LieKind.RED_HERRING_EVASION]
            # Honest confusion (D-009): innocent, non-lying suspects whose single-location claim
            # misses a place they actually visited during the window.
            lied = {a.claim_id for a in t3.lie_annotations}
            for claim in bundle.t1_session.recorded_claims:
                if claim.speaker_id == t3.culprit_id or claim.claim_id in lied:
                    continue
                counts["honest_innocent_claims"] += 1
                visited = {
                    e.location_id
                    for e in t3.canonical_events
                    if e.event_kind == "MOVEMENT"
                    and e.actor_id == claim.speaker_id
                    and t3.crime_window.start_min - bundle.config.tick_size_min < e.tick_min <= t3.crime_window.end_min
                }
                counts["honest_confusion"] += bool(visited - {claim.claimed_location_id})
            murder = next(e for e in t3.canonical_events if e.event_kind == "MURDER")
            selection_probs.append(float(murder.metadata.get("selection_probability", 1.0)))

            rules: dict[str, dict[str, float]] = {
                "motive evidence": rule_motive(bundle),
                "crime-scene presence in window": rule_scene_presence(bundle),
                "has forensic trace": rule_has_forensic(bundle),
                "validator support score": rule_validator_support(bundle, tpl),
            }
            for name, scores in rules.items():
                credits.setdefault(name, []).append(top1_credit(scores, t3.culprit_id))
                if report.is_valid:
                    credits.setdefault(f"{name} [valid only]", []).append(top1_credit(scores, t3.culprit_id))

    n = counts["cases"]
    return {
        "cases": n,
        "templates": len(load_all_templates()),
        "chance_top1": round(1 / num_suspects, 3),
        "rule_top1": {k: round(mean(v), 3) for k, v in credits.items()},
        "culprit_lie_rate": round(counts["culprit_lied"] / n, 3),
        "honest_confusion_rate": round(counts["honest_confusion"] / max(1, counts["honest_innocent_claims"]), 3),
        "mean_culprit_selection_probability": round(mean(selection_probs), 3),
        "share_single_eligible_suspect": round(sum(p >= 0.9999 for p in selection_probs) / n, 3),
        "counts": dict(sorted(counts.items())),
        "note": "Synthetic-data scores measure recovery of the generator's logic.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=50, help="seeds per template")
    parser.add_argument("--out", type=Path, default=None, help="optional JSON output path")
    args = parser.parse_args()
    result = run(seeds=args.seeds)
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")


if __name__ == "__main__":
    main()
