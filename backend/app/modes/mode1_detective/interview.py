# backend/app/modes/mode1_detective/interview.py
"""
Interview mechanics shared by play, the dataset generator and experiments (no dependency on the ranker):
apply one question or record request to a session state and classify what happened.
An evasive answer is RECORDED as a claim without a location ("I don't remember"), so models can see it.
"""
import random
from datetime import UTC, datetime, timedelta

from app.domain.simulation import SimulatedCaseBundle
from app.domain.tiers import T1Session
from app.domain.world import Claim, TimeInterval
from app.engine.consistency import StructuredConsistencyEngine
from app.engine.observation import ALIBI_PHRASES_ALONE
from app.engine.reveal_sampler import EvidenceRevealSampler
from app.modes.mode1_detective.players import Behaviour, answer_location
from app.modes.mode1_detective.questions import ASK, CHECK, Action

EVASIVE_TEXT = "I don't remember."

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
    claim = Claim(
        claim_id=f"claim_{bundle.config.case_id}_{action.suspect_id}_q{turn}",
        case_id=bundle.config.case_id,
        speaker_id=action.suspect_id,
        subject_id=action.suspect_id,
        turn_index=turn,
        # Deterministic, never the wall clock: same seed, same dataset (caught by the checksum test).
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=bundle.config.end_min + turn),
        claimed_location_id=loc,
        claimed_time_interval=TimeInterval(start_min=action.minute, end_min=action.minute),
        free_text=EVASIVE_TEXT if loc is None else ALIBI_PHRASES_ALONE[0].format(
            loc=loc, start=action.minute, end=action.minute
        ),
    )
    setting = bundle.setting
    if loc is None:
        outcome = "evasive"
    elif StructuredConsistencyEngine.check_claim_against_facts(claim, t1.discovered_facts, setting):
        outcome = "refuted"
    elif StructuredConsistencyEngine.check_claim_against_claims(claim, t1.recorded_claims, setting):
        outcome = "self_contradiction"
    else:
        outcome = "consistent"
    return t1.model_copy(update={"recorded_claims": [*t1.recorded_claims, claim]}), outcome
