# backend/tests/test_dataset_generator.py
from pathlib import Path

import pytest

from app.engine.dataset_generator import DatasetGenerator, save_dataset
from app.engine.reveal_sampler import (
    sample_reveal_snapshots,
)
from app.engine.templates import generate_valid_case, get_template


def test_reveal_monotonicity_and_convergence() -> None:
    """
    Task 3.1 (Reveal Monotonicity):
    For a single case and `order_idx`, verify that as `reveal_fraction` increases
    (0.35 -> 0.65 -> 1.0), the set of `discovered_facts` and `recorded_claims` in
    `t1_partial` is strictly non-decreasing (earlier facts never disappear), and at
    `1.0` it equals the full `bundle.t1_session`.
    """
    manor = get_template("manor")
    _, bundle, report = generate_valid_case(template=manor, base_seed=42, num_suspects=4)
    assert report.is_valid is True

    snapshots = sample_reveal_snapshots(
        bundle=bundle,
        template=manor,
        split="train",
        num_orderings=2,
        stage_fractions=(0.35, 0.65, 1.0),
    )

    # num_orderings=2 across (0.35, 0.65) + 1 converged stage at 1.0 = 5 snapshots
    assert len(snapshots) == 5

    # All snapshots from the same case must carry the exact same split and metadata
    for snap in snapshots:
        assert snap.case_id == bundle.config.case_id
        assert snap.template_id == "manor"
        assert snap.split == "train"
        assert snap.culprit_id == bundle.t3_canonical.culprit_id
        assert snap.crime_location_id == bundle.t0_public.crime_location_id
        assert snap.murder_window == bundle.t0_public.crime_window

    full_stage_snaps = [s for s in snapshots if s.reveal_fraction == 1.0]
    assert len(full_stage_snaps) == 1
    full_snap = full_stage_snaps[0]

    # At reveal_fraction == 1.0, t1_partial equals the full bundle.t1_session
    assert full_snap.t1_partial == bundle.t1_session
    full_fact_ids = {f.fact_id for f in bundle.t1_session.discovered_facts}
    full_claim_ids = {c.claim_id for c in bundle.t1_session.recorded_claims}
    assert {f.fact_id for f in full_snap.t1_partial.discovered_facts} == full_fact_ids
    assert {c.claim_id for c in full_snap.t1_partial.recorded_claims} == full_claim_ids

    # Check monotonicity across stages (0.35 -> 0.65 -> 1.0) for each ordering
    for order_idx in (0, 1):
        ord_partial_snaps = sorted(
            [s for s in snapshots if s.order_idx == order_idx and s.reveal_fraction < 1.0],
            key=lambda s: s.reveal_fraction,
        )
        assert [s.reveal_fraction for s in ord_partial_snaps] == [0.35, 0.65]

        stage_sequence = [*ord_partial_snaps, full_snap]
        for prev_snap, next_snap in zip(stage_sequence, stage_sequence[1:], strict=False):
            prev_facts = {f.fact_id for f in prev_snap.t1_partial.discovered_facts}
            next_facts = {f.fact_id for f in next_snap.t1_partial.discovered_facts}
            assert len(prev_facts) >= 1, "Stage 0 must include at least 1 baseline briefing fact"
            assert prev_facts.issubset(next_facts), (
                f"Facts disappeared between fraction {prev_snap.reveal_fraction} and "
                f"{next_snap.reveal_fraction} in order_idx={order_idx}"
            )
            assert len(prev_facts) <= len(next_facts)

            prev_claims = {c.claim_id for c in prev_snap.t1_partial.recorded_claims}
            next_claims = {c.claim_id for c in next_snap.t1_partial.recorded_claims}
            assert prev_claims.issubset(next_claims), (
                f"Claims disappeared between fraction {prev_snap.reveal_fraction} and "
                f"{next_snap.reveal_fraction} in order_idx={order_idx}"
            )
            assert len(prev_claims) <= len(next_claims)


@pytest.fixture(scope="module")
def small_dataset():
    return DatasetGenerator.generate_dataset(total_cases=72, master_seed=2026, ood_shifted_cases=6)


def test_splits_follow_prd_8_4(small_dataset) -> None:
    """
    PRD 8.3/8.4: dev-template cases split by case into train/val/test_in_dist; held-out templates only
    in test_held_out_template and test_ood_shifted; every snapshot of a case shares its split.
    """
    snapshots, manifest = small_dataset
    held_out = set(manifest.templates_by_group["test_held_out_template"])
    assert held_out == {"train", "lodge", "abbey"}
    assert manifest.num_templates_total == 12
    assert manifest.num_cases_total == 72 + 6

    split_of_case: dict[str, str] = {}
    templates_by_split: dict[str, set[str]] = {}
    for snap in snapshots:
        assert split_of_case.setdefault(snap.case_id, snap.split) == snap.split
        templates_by_split.setdefault(snap.split, set()).add(snap.template_id)
    for split in ("train", "val", "test_in_dist"):
        assert templates_by_split[split] and templates_by_split[split].isdisjoint(held_out)
    assert templates_by_split["test_held_out_template"] == held_out
    assert templates_by_split["test_ood_shifted"] <= held_out
    assert sum(manifest.cases_by_split.values()) == manifest.num_cases_total


def test_cv_folds_partition_train_cases_by_template(small_dataset) -> None:
    snapshots, manifest = small_dataset
    fold_of_template = {tid: int(fold) for fold, tids in manifest.cv_folds.items() for tid in tids}
    assert set(fold_of_template) == set(manifest.templates_by_group["dev"])
    assert len(set(fold_of_template.values())) == 3
    for snap in snapshots:
        if snap.split == "train":
            assert snap.cv_fold == fold_of_template[snap.template_id]
        else:
            assert snap.cv_fold is None


def test_shifted_ood_cases_are_outside_training_ranges(small_dataset) -> None:
    from app.engine.templates import CASE_VARIABLE_RANGES

    snapshots, _ = small_dataset
    shifted = [s for s in snapshots if s.split == "test_ood_shifted"]
    assert shifted
    for snap in shifted:
        assert snap.murder_window.duration > CASE_VARIABLE_RANGES["murder_window_length_min"][1]


def test_feature_table_has_one_culprit_per_evidence_state(small_dataset) -> None:
    snapshots, _ = small_dataset
    rows = DatasetGenerator.feature_rows(snapshots)
    per_state: dict[tuple, int] = {}
    for row in rows:
        key = (row["case_id"], row["order_idx"], row["stage_idx"])
        per_state[key] = per_state.get(key, 0) + int(row["label"])
    assert len(per_state) == len(snapshots)
    assert set(per_state.values()) == {1}


def test_determinism_checksums_and_round_trip(tmp_path: Path) -> None:
    """PRD 10.3: same master seed -> identical dataset files (checksums); save/load round-trips."""
    a_snaps, a_manifest = DatasetGenerator.generate_dataset(total_cases=24, master_seed=123, ood_shifted_cases=3)
    b_snaps, b_manifest = DatasetGenerator.generate_dataset(total_cases=24, master_seed=123, ood_shifted_cases=3)
    assert a_manifest == b_manifest and a_snaps == b_snaps

    a_paths = save_dataset(a_snaps, a_manifest, tmp_path / "a")
    b_paths = save_dataset(b_snaps, b_manifest, tmp_path / "b")
    for key in ("snapshots_path", "features_path", "manifest_path"):
        assert a_paths[key].read_bytes() == b_paths[key].read_bytes()

    loaded_snaps, loaded_manifest = DatasetGenerator.load_dataset(tmp_path / "a")
    assert loaded_snaps == a_snaps
    assert loaded_manifest.checksums["features.csv"]
    assert loaded_manifest.feature_spec_version == a_manifest.feature_spec_version


def test_interview_states_are_in_the_case_split_and_carry_answers(small_dataset) -> None:
    """D-029: interview states (after 2, 4, 6 questions) belong to their case's split and contain answers."""
    snapshots, _ = small_dataset
    split_of_case = {s.case_id: s.split for s in snapshots if s.interview_turns == 0}
    interview = [s for s in snapshots if s.interview_turns > 0]
    assert interview and {s.interview_turns for s in interview} == {2, 4, 6}
    for snap in interview:
        assert snap.split == split_of_case[snap.case_id]
        answers = [c for c in snap.t1_partial.recorded_claims if c.turn_index >= 1]
        checks = snap.interview_turns - len(answers)
        assert 0 <= checks <= snap.interview_turns  # each action is a question (answer) or a record request


def test_dodging_questions_is_not_a_tell_in_training_interviews(small_dataset) -> None:
    """Lesson of D-023: culprits and innocents must dodge at about the same rate in the training data."""
    snapshots, _ = small_dataset
    dodged = {"culprit": [0, 0], "innocent": [0, 0]}
    for snap in snapshots:
        if snap.interview_turns != 6:
            continue
        for c in snap.t1_partial.recorded_claims:
            if c.turn_index >= 1:
                role = "culprit" if c.speaker_id == snap.culprit_id else "innocent"
                dodged[role][0] += c.claimed_location_id is None
                dodged[role][1] += 1
    rates = {r: d / n for r, (d, n) in dodged.items() if n}
    assert abs(rates["culprit"] - rates["innocent"]) < 0.12, rates
