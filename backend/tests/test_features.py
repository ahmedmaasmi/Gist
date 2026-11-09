# backend/tests/test_features.py
"""PRD 5.3: feature spec v1 — deterministic, versioned, T1-only, exclusion list enforced."""
import inspect
import math
import re
from pathlib import Path

import pytest

from app.domain.character import RevealedRelationship
from app.domain.enums import EvidenceCategory, ProvenanceClass, RelationshipTag
from app.domain.setting import Location, SettingTemplate
from app.domain.tiers import T0Public, T1Session
from app.domain.world import Claim, Fact, TimeInterval
from app.engine.reveal_sampler import sample_reveal_snapshots
from app.engine.templates import generate_valid_case, get_template
from app.features import FEATURE_GROUPS, FEATURE_SPEC_VERSION, FEATURES, compute_suspect_features
from app.features.spec import EXCLUDED_NAME_TOKENS

FEATURES_DOC = Path(__file__).resolve().parents[2] / "docs" / "FEATURES.md"
NAMES = [f.name for f in FEATURES]


def test_spec_and_document_are_in_sync():
    doc = FEATURES_DOC.read_text()
    assert f"Version: {FEATURE_SPEC_VERSION}" in doc
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", doc, flags=re.MULTILINE))
    assert documented == set(NAMES)


def test_feature_names_respect_exclusion_list():
    assert len(NAMES) == len(set(NAMES))
    for name in NAMES:
        assert not set(name.split("_")) & EXCLUDED_NAME_TOKENS, name
    assert set(FEATURE_GROUPS) == {"A", "B", "C", "context"}


def test_feature_function_can_only_see_t0_t1_and_setting():
    """Structural guarantee: there is no parameter through which T2/T3 data could arrive."""
    params = inspect.signature(compute_suspect_features).parameters
    assert [p.annotation for p in params.values()] == [T0Public, T1Session, SettingTemplate]


@pytest.fixture(scope="module")
def manor_case():
    _, bundle, _ = generate_valid_case(get_template("manor"), base_seed=42)
    return bundle


def test_rows_are_deterministic_complete_and_finite(manor_case):
    tpl = get_template("manor")
    a = compute_suspect_features(manor_case.t0_public, manor_case.t1_session, tpl)
    b = compute_suspect_features(manor_case.t0_public, manor_case.t1_session, tpl)
    assert a == b
    assert [r.suspect_id for r in a] == manor_case.t0_public.suspect_ids
    for row in a:
        assert list(row.features) == NAMES
        assert row.feature_spec_version == FEATURE_SPEC_VERSION
        assert all(math.isfinite(v) for v in row.features.values())


def test_partial_evidence_never_exceeds_full_evidence(manor_case):
    """Features of an early evidence state can only use what was revealed by then (PRD 8.8)."""
    tpl = get_template("manor")
    full = {r.suspect_id: r.features for r in compute_suspect_features(manor_case.t0_public, manor_case.t1_session, tpl)}
    additive = ["motive_evidence", "access_evidence", "scene_presence_in_window", "victim_relationship_records"]
    for snap in sample_reveal_snapshots(manor_case, template=tpl, split="train"):
        for row in compute_suspect_features(manor_case.t0_public, snap.t1_partial, tpl):
            for name in additive:
                assert row.features[name] <= full[row.suspect_id][name] + 1e-9


def _setting() -> SettingTemplate:
    return SettingTemplate(
        template_id="tpl_tiny",
        name="Tiny Manor",
        locations=[
            Location(location_id="loc_study", name="Study", is_restricted=True),
            Location(location_id="loc_library", name="Library"),
            Location(location_id="loc_gatehouse", name="Gatehouse"),
        ],
        travel_matrix={
            "loc_study": {"loc_library": 2, "loc_gatehouse": 17},
            "loc_library": {"loc_study": 2, "loc_gatehouse": 15},
            "loc_gatehouse": {"loc_library": 15, "loc_study": 17},
        },
    )


def _fact(fid, subject, category, loc=None, minute=None, target=None, rel=0.9, prov=ProvenanceClass.RECORD):
    return Fact(
        fact_id=fid, case_id="c", description=fid, subject_id=subject, target_id=target, location_id=loc,
        time_interval=None if minute is None else TimeInterval(start_min=minute, end_min=minute),
        category=category, provenance=prov, reliability=rel,
    )


def test_hand_computed_values():
    window = TimeInterval(start_min=1260, end_min=1280)
    t0 = T0Public(case_id="c", victim_id="v", crime_location_id="loc_study", crime_window=window,
                  suspect_ids=["a", "b"])
    facts = [
        _fact("m1", "a", EvidenceCategory.MOTIVE, target="v", rel=0.8),
        _fact("m2", "b", EvidenceCategory.MOTIVE, target="someone_else", rel=0.8),  # not about the victim
        _fact("s1", "a", EvidenceCategory.ACCESS, loc="loc_study", minute=1270, rel=0.9),
        _fact("s2", "a", EvidenceCategory.ACCESS, loc="loc_study", minute=1200, rel=0.9),  # outside window
        _fact("g1", "b", EvidenceCategory.TIMELINE, loc="loc_gatehouse", minute=1265, prov=ProvenanceClass.PHYSICAL),
        _fact("rel", "a", EvidenceCategory.RELATIONSHIP, target="v"),
    ]
    claims = [
        Claim(claim_id="ca", case_id="c", speaker_id="a", subject_id="a", turn_index=0,
              claimed_location_id="loc_library", claimed_time_interval=window),
        Claim(claim_id="cb", case_id="c", speaker_id="b", subject_id="b", turn_index=0,
              claimed_location_id="loc_gatehouse", claimed_time_interval=window, has_corroboration_claim=True),
    ]
    t1 = T1Session(case_id="c", discovered_facts=facts, recorded_claims=claims,
                   revealed_edges=[RevealedRelationship(source_id="a", target_id="v",
                                                        tags=[RelationshipTag.RIVAL], evidence_fact_id="rel")])
    a, b = (r.features for r in compute_suspect_features(t0, t1, _setting()))

    assert a["motive_evidence"] == pytest.approx(0.8)
    assert b["motive_evidence"] == 0.0
    assert a["victim_relationship_records"] == 1.0
    assert a["access_evidence"] == pytest.approx(1.8)            # both study records, any time
    assert a["scene_presence_in_window"] == pytest.approx(0.9)   # only the one inside the window
    assert a["opportunity_overlap"] == 1.0                       # no record elsewhere
    # b's gatehouse sighting at 1265 is 17 min from the study: rules out 1260..1280 entirely
    assert b["opportunity_overlap"] == 0.0
    # a claims the library all window, but a study record at 1270 refutes it
    assert a["claim_fact_conflicts"] == 1.0 and a["unverified_claim_share"] == 1.0
    assert a["alibi_strength"] == 0.0
    # b's gatehouse claim is supported by the gatehouse record
    assert b["claim_fact_conflicts"] == 0.0 and b["unverified_claim_share"] == 0.0
    assert b["alibi_strength"] == pytest.approx(0.9)
    assert (a["claimed_corroboration_share"], b["claimed_corroboration_share"]) == (0.0, 1.0)
    assert a["evidence_coverage"] == pytest.approx(4 / 5) == b["evidence_coverage"]  # no FORENSIC
