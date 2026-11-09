# backend/tests/test_generator_properties.py
"""
Step 2 audit: properties the role-free case generator must keep (PRD 7A, 8.2, CH-02, CH-03).
"""
import random
from collections import Counter

import pytest

from app.domain.enums import LieKind
from app.engine.observation import ALIBI_PHRASES_ALONE, ALIBI_PHRASES_WITH
from app.engine.simulator import SocialSimulator
from app.engine.templates import get_template, load_all_templates, sample_case_setup_from_template

TEMPLATE_IDS = sorted(load_all_templates())


def _bundle(template_id: str, seed: int):
    return sample_case_setup_from_template(template=get_template(template_id), seed=seed).simulate()


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_ch03_same_seed_same_case(template_id):
    a, b = _bundle(template_id, 11), _bundle(template_id, 11)
    assert a.log_hash == b.log_hash
    assert a.t1_session.model_dump_json() == b.t1_session.model_dump_json()
    assert a.t3_canonical.model_dump_json() == b.t3_canonical.model_dump_json()
    assert _bundle(template_id, 12).log_hash != a.log_hash


def test_ch02_every_event_explains_itself():
    for template_id in TEMPLATE_IDS:
        for event in _bundle(template_id, 3).canonical_events:
            assert event.reason_string.strip()
            if event.event_kind == "INTERACTION":
                assert "prob=" in event.reason_string and "roll=" in event.reason_string
            if event.event_kind == "MURDER":
                assert "selection_probability=" in event.reason_string


def test_culprit_sampling_follows_softmax_and_respects_opportunity():
    # (total, motive, opportunity, low_composure)
    scores = {"a": (2.0, 1.0, 0.5, 0.5), "b": (1.0, 0.2, 0.5, 0.3), "c": (9.0, 5.0, 0.0, 4.0)}
    rng = random.Random(0)
    picks = Counter(SocialSimulator._sample_culprit(scores, 0.5, rng)[0] for _ in range(4000))
    assert picks["c"] == 0, "A suspect who cannot reach the scene must never be chosen"
    # softmax([2, 1] / 0.5): P(a) = e^4 / (e^4 + e^2) ~= 0.881
    assert abs(picks["a"] / 4000 - 0.881) < 0.03


def test_most_suspicious_suspect_is_not_always_guilty():
    probs = []
    for template_id in TEMPLATE_IDS:
        for seed in range(5):
            murder = next(e for e in _bundle(template_id, seed).canonical_events if e.event_kind == "MURDER")
            probs.append(float(murder.metadata["selection_probability"]))
    assert min(probs) < 0.5 < max(probs)


def test_alibi_wording_never_reveals_the_role():
    """Every alibi text must be a shared-pool phrase filled only with the claim's own content."""
    seen_kinds = set()
    for template_id in TEMPLATE_IDS:
        for seed in range(5):
            bundle = _bundle(template_id, seed)
            kinds = {a.claim_id: a.kind for a in bundle.t3_canonical.lie_annotations}
            for claim in bundle.t1_session.recorded_claims:
                window = claim.claimed_time_interval
                pool = ALIBI_PHRASES_WITH if claim.observed_character_ids else ALIBI_PHRASES_ALONE
                allowed = {
                    p.format(
                        loc=claim.claimed_location_id,
                        others=", ".join(claim.observed_character_ids),
                        start=window.start_min,
                        end=window.end_min,
                    )
                    for p in pool
                }
                assert claim.free_text in allowed
                seen_kinds.add(kinds.get(claim.claim_id, "HONEST"))
    assert {"HONEST", LieKind.CULPRIT_COVER_STORY, LieKind.COVER_FOR} <= seen_kinds


def test_motive_evidence_is_worded_the_same_for_culprit_and_innocents():
    for template_id in TEMPLATE_IDS:
        bundle = _bundle(template_id, 5)
        t1_text = bundle.t1_session.model_dump_json()
        assert "crime-linked" not in t1_text
        # Only the culprit's secrets about the victim are marked as the cause of the murder (T3 truth)
        for cid, pack in bundle.t2_knowledge.items():
            if pack.character is None:
                continue
            for secret in pack.character.secrets:
                if secret.is_crime_linked:
                    assert cid == bundle.t3_canonical.culprit_id
                    assert secret.involves_character_id == bundle.config.victim_id


def test_honest_confusion_occurs_without_lie_annotations():
    """D-009: innocents who moved during the window can make inaccurate but honest claims."""
    found = False
    for template_id in TEMPLATE_IDS:
        for seed in range(10):
            bundle = _bundle(template_id, seed)
            t3 = bundle.t3_canonical
            lied = {a.claim_id for a in t3.lie_annotations}
            for claim in bundle.t1_session.recorded_claims:
                if claim.speaker_id == t3.culprit_id or claim.claim_id in lied:
                    continue
                visited = {
                    e.location_id
                    for e in t3.canonical_events
                    if e.event_kind == "MOVEMENT"
                    and e.actor_id == claim.speaker_id
                    and t3.crime_window.start_min - 10 < e.tick_min <= t3.crime_window.end_min
                }
                found |= bool(visited - {claim.claimed_location_id})
    assert found


def test_culprit_is_physically_possible_and_has_a_motive():
    """
    Regression for the hand-check of 20 manor seeds: culprits used to 'teleport' to the scene
    (then the solver eliminated them) and some had no motive at all.
    """
    from app.engine.solver import SymbolicTimelineSolver

    for template_id in TEMPLATE_IDS:
        tpl = get_template(template_id)
        for seed in range(10):
            bundle = _bundle(template_id, seed)
            t3 = bundle.t3_canonical
            eliminated = SymbolicTimelineSolver.find_eliminated_suspects(
                t0=bundle.t0_public, t1=bundle.t1_session, setting=tpl
            )
            assert t3.culprit_id not in eliminated, eliminated.get(t3.culprit_id)
            murder = next(e for e in t3.canonical_events if e.event_kind == "MURDER")
            assert float(murder.metadata["motive_score"]) > 0.0
