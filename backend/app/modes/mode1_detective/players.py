# backend/app/modes/mode1_detective/players.py
"""
PRD 9.3 player simulator: scripted suspects who answer the detective's questions. They answer from the
hidden truth (T3 events), exactly as a human player who knows what their character did would.

Behaviours:
  honest     says where they really were
  lying      during the crime window, repeats their own initial alibi (the cover story); truthful outside it
  evasive    with probability EVASION_RATE answers "I don't remember" (no claim); otherwise honest

Populations (who behaves how):
  honest_innocents   culprit lying, innocents honest
  evasive_innocents  culprit lying, innocents evasive
  mixed              as generated: anyone with an intentional-lie annotation keeps their story; innocents
                     are also evasive with probability MIXED_EVASION_RATE
"""
import random
from dataclasses import dataclass

from app.domain.enums import LieKind
from app.domain.simulation import SimulatedCaseBundle

POPULATIONS = ("honest_innocents", "evasive_innocents", "mixed")
EVASION_RATE = 0.5
MIXED_EVASION_RATE = 0.25


@dataclass(frozen=True)
class Behaviour:
    keeps_cover_story: bool
    evasion_rate: float


def behaviours(bundle: SimulatedCaseBundle, population: str) -> dict[str, Behaviour]:
    culprit = bundle.t3_canonical.culprit_id
    liars = {a.liar_id for a in bundle.t3_canonical.lie_annotations}
    out = {}
    for s in bundle.t0_public.suspect_ids:
        if population == "honest_innocents":
            out[s] = Behaviour(keeps_cover_story=s == culprit, evasion_rate=0.0)
        elif population == "evasive_innocents":
            out[s] = Behaviour(keeps_cover_story=s == culprit, evasion_rate=0.0 if s == culprit else EVASION_RATE)
        elif population == "mixed":
            culprit_lies = any(
                a.liar_id == culprit and a.kind == LieKind.CULPRIT_COVER_STORY for a in bundle.t3_canonical.lie_annotations
            )
            keeps = culprit_lies if s == culprit else s in liars
            out[s] = Behaviour(keeps_cover_story=keeps, evasion_rate=0.0 if s == culprit else MIXED_EVASION_RATE)
        else:
            raise ValueError(population)
    return out


def true_location(bundle: SimulatedCaseBundle, suspect_id: str, minute: int) -> str | None:
    """Where the suspect really was at `minute` (last movement at or before it), from the T3 event log."""
    loc = None
    for e in bundle.t3_canonical.canonical_events:
        if e.event_kind == "MOVEMENT" and e.actor_id == suspect_id and e.tick_min <= minute:
            loc = e.location_id
    return loc


def cover_story_location(bundle: SimulatedCaseBundle, suspect_id: str) -> str | None:
    """The location in the suspect's own initial alibi claim (their story, whether true or not)."""
    for c in bundle.t1_session.recorded_claims:
        if c.speaker_id == suspect_id and c.subject_id == suspect_id:
            return c.claimed_location_id
    return None


def answer_location(
    bundle: SimulatedCaseBundle, behaviour: Behaviour, suspect_id: str, minute: int, rng: random.Random
) -> str | None:
    """The location the suspect claims for `minute`, or None if they evade."""
    if behaviour.evasion_rate and rng.random() < behaviour.evasion_rate:
        return None
    window = bundle.t0_public.crime_window
    if behaviour.keeps_cover_story and window is not None and window.contains(minute):
        story = cover_story_location(bundle, suspect_id)
        if story is not None:
            return story
    return true_location(bundle, suspect_id, minute)
