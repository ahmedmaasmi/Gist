# backend/app/modes/mode1_detective/episode.py
"""
PRD 6.3 gameplay loop, simulated: the policy picks an action, the (simulated) player answers or records are
revealed, the consistency engine checks the new claim, and the ranker produces a new distribution.
"""
import random
from dataclasses import dataclass, field

from app.domain.simulation import SimulatedCaseBundle
from app.domain.tiers import T1Session
from app.domain.world import Claim, TimeInterval
from app.engine.consistency import StructuredConsistencyEngine
from app.engine.observation import ALIBI_PHRASES_ALONE
from app.engine.reveal_sampler import EvidenceRevealSampler
from app.ml.ranker import Ranker
from app.modes.mode1_detective.players import Behaviour, answer_location, behaviours
from app.modes.mode1_detective.questions import ASK, CHECK, Action, build_question_bank

OUTCOMES = {
    ASK: ("consistent", "refuted", "self_contradiction", "evasive"),
    CHECK: ("scene_record", "other_record", "nothing"),
}


START_FRACTION = 0.15  # E3 starting evidence (pre-registered in docs/EXPERIMENTS.md)


def initial_state(bundle: SimulatedCaseBundle, fraction: float = START_FRACTION) -> T1Session:
    """The investigation starts from an early evidence state (`fraction` of the evidence, first ordering)."""
    snaps = EvidenceRevealSampler.sample_reveal_snapshots(
        bundle=bundle, template=bundle.setting, split="test_held_out_template", num_orderings=1,
        stage_fractions=(fraction, 1.0),
    )
    return min(snaps, key=lambda s: s.reveal_fraction).t1_partial


def apply_action(
    bundle: SimulatedCaseBundle,
    t1: T1Session,
    action: Action,
    who: dict[str, Behaviour],
    rng: random.Random,
    turn: int,
) -> tuple[T1Session, str]:
    """Returns the new session state and the observed outcome category."""
    if action.kind == CHECK:
        known = {f.fact_id for f in t1.discovered_facts}
        new = [f for f in bundle.t1_session.discovered_facts if f.subject_id == action.suspect_id and f.fact_id not in known]
        new_ids = {f.fact_id for f in new}
        edges = [r for r in bundle.t1_session.revealed_edges if r.evidence_fact_id in new_ids]
        window, scene = bundle.t0_public.crime_window, bundle.t0_public.crime_location_id
        at_scene = any(
            f.location_id == scene and f.time_interval is not None and f.time_interval.overlaps(window) for f in new
        )
        outcome = "scene_record" if at_scene else ("other_record" if new else "nothing")
        return (
            t1.model_copy(update={
                "discovered_facts": [*t1.discovered_facts, *new],
                "revealed_edges": [*t1.revealed_edges, *edges],
            }),
            outcome,
        )

    loc = answer_location(bundle, who[action.suspect_id], action.suspect_id, action.minute, rng)
    if loc is None:
        return t1, "evasive"
    claim = Claim(
        claim_id=f"claim_{bundle.config.case_id}_{action.suspect_id}_q{turn}",
        case_id=bundle.config.case_id,
        speaker_id=action.suspect_id,
        subject_id=action.suspect_id,
        turn_index=turn,
        claimed_location_id=loc,
        claimed_time_interval=TimeInterval(start_min=action.minute, end_min=action.minute),
        free_text=ALIBI_PHRASES_ALONE[0].format(loc=loc, start=action.minute, end=action.minute),
    )
    setting = bundle.setting
    if StructuredConsistencyEngine.check_claim_against_facts(claim, t1.discovered_facts, setting):
        outcome = "refuted"
    elif StructuredConsistencyEngine.check_claim_against_claims(claim, t1.recorded_claims, setting):
        outcome = "self_contradiction"
    else:
        outcome = "consistent"
    return t1.model_copy(update={"recorded_claims": [*t1.recorded_claims, claim]}), outcome


@dataclass
class EpisodeResult:
    case_id: str
    culprit_id: str
    correct_by_step: list[bool]  # leading suspect correct after 0..budget actions
    actions: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    decision_logs: list[list[tuple[str, float]]] = field(default_factory=list)  # MD-03

    @property
    def reach_and_hold(self) -> int:
        """Fewest actions after which the leading suspect is correct and stays correct (budget+1 if never)."""
        k = len(self.correct_by_step)
        while k > 0 and self.correct_by_step[k - 1]:
            k -= 1
        return k if self.correct_by_step[-1] else len(self.correct_by_step)


def run_episode(
    bundle: SimulatedCaseBundle,
    policy,
    population: str,
    ranker: Ranker,
    budget: int = 8,
    seed: int = 0,
    start_fraction: float = START_FRACTION,
) -> EpisodeResult:
    rng = random.Random(seed)
    who = behaviours(bundle, population)
    t0, t1 = bundle.t0_public, initial_state(bundle, start_fraction)
    remaining = build_question_bank(t0)
    culprit = bundle.t3_canonical.culprit_id

    def leader_correct(probs: dict[str, float]) -> bool:
        best = max(probs.values())
        return [s for s, p in probs.items() if p == best] == [culprit]

    probs = ranker.rank(t0, t1, bundle.setting).probabilities
    result = EpisodeResult(bundle.config.case_id, culprit, [leader_correct(probs)])
    for turn in range(1, budget + 1):
        action, considered = policy.choose(t0, t1, probs, remaining, rng)
        remaining = [a for a in remaining if a != action]
        t1, outcome = apply_action(bundle, t1, action, who, rng, turn)
        probs = ranker.rank(t0, t1, bundle.setting).probabilities
        result.actions.append(action.label())
        result.outcomes.append(outcome)
        result.decision_logs.append(considered)
        result.correct_by_step.append(leader_correct(probs))
    return result
