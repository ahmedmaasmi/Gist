# backend/tests/test_dataset_generator.py
from pathlib import Path

from app.engine.dataset_generator import (
    DatasetGenerator,
    DatasetManifest,
    generate_dataset,
    save_dataset,
)
from app.engine.reveal_sampler import (
    EvidenceRevealSampler,
    EvidenceStateSnapshot,
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
        for prev_snap, next_snap in zip(stage_sequence, stage_sequence[1:]):
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


def test_strict_case_level_split_isolation_and_template_isolation() -> None:
    """
    Task 3.2 & 3.3 (PRD Section 8.3 & 8.4):
    - Generate a test dataset of 40 cases (~200 snapshots).
    - Assert that the sets of `case_id`s in 'train', 'val', 'test_in_dist', and
      'test_held_out_template' are 100% mutually disjoint (zero overlap across splits).
    - Assert that 'train' and 'val' splits contain ZERO snapshots from 'train'
      (Night Express) or 'lodge' (Alpine Lodge) templates, and 'test_held_out_template'
      contains ONLY those held-out templates.
    """
    snapshots, manifest = generate_dataset(
        total_cases=40,
        master_seed=2026,
        hard_case_ratio=0.10,
        num_orderings=2,
    )

    # 40 cases * 5 snapshots/case = 200 snapshots
    assert manifest.num_cases_total == 40
    assert manifest.num_templates_total == 8
    assert len(snapshots) == 200
    assert sum(manifest.cases_by_split.values()) == 40
    assert sum(manifest.snapshots_by_split.values()) == 200

    # Group case_ids and template_ids by split
    cases_by_split: dict[str, set[str]] = {
        "train": set(),
        "val": set(),
        "test_in_dist": set(),
        "test_held_out_template": set(),
    }
    templates_by_split: dict[str, set[str]] = {
        "train": set(),
        "val": set(),
        "test_in_dist": set(),
        "test_held_out_template": set(),
    }

    for snap in snapshots:
        cases_by_split[snap.split].add(snap.case_id)
        templates_by_split[snap.split].add(snap.template_id)

    # Every split must be populated
    for split_name, case_set in cases_by_split.items():
        assert len(case_set) > 0, f"Expected non-empty split '{split_name}'"
        assert len(case_set) == manifest.cases_by_split[split_name]

    # Strict Case-Level Split Isolation: 100% mutually disjoint case_ids across all splits
    split_names = list(cases_by_split.keys())
    for i in range(len(split_names)):
        for j in range(i + 1, len(split_names)):
            split_a = split_names[i]
            split_b = split_names[j]
            overlap = cases_by_split[split_a] & cases_by_split[split_b]
            assert overlap == set(), (
                f"Case leakage detected between '{split_a}' and '{split_b}': {overlap}"
            )

    # Union of all split case_ids equals 40 unique cases
    all_unique_cases = set().union(*cases_by_split.values())
    assert len(all_unique_cases) == 40

    # Strict Template-Held-Out Isolation (PRD 8.4)
    held_out_template_ids = {"train", "lodge"}
    assert templates_by_split["train"].isdisjoint(held_out_template_ids)
    assert templates_by_split["val"].isdisjoint(held_out_template_ids)
    assert templates_by_split["test_in_dist"].isdisjoint(held_out_template_ids)
    assert templates_by_split["test_held_out_template"] == held_out_template_ids
    assert templates_by_split["val"] == {"yacht", "warehouse"}
    assert templates_by_split["train"] <= {"manor", "office", "clinic", "gallery"}
    assert templates_by_split["test_in_dist"] <= {"manor", "office", "clinic", "gallery"}


def test_determinism_and_manifest_honesty(tmp_path: Path) -> None:
    """
    Task 3.4 (PRD Section 8.1 & 10.3):
    Running `generate_dataset(total_cases=24, master_seed=123)` twice yields the
    exact same `DatasetManifest` and snapshot IDs, and the manifest explicitly
    records both `num_templates_total` and `num_cases_total`.
    Also verifies `save_dataset` and `load_dataset` round-trip persistence.
    """
    snapshots_a, manifest_a = DatasetGenerator.generate_dataset(
        total_cases=24,
        master_seed=123,
        hard_case_ratio=0.10,
        num_orderings=2,
    )
    snapshots_b, manifest_b = DatasetGenerator.generate_dataset(
        total_cases=24,
        master_seed=123,
        hard_case_ratio=0.10,
        num_orderings=2,
    )

    # Exact manifest determinism & honest framing (PRD 8.1 & 10.3)
    assert manifest_a == manifest_b
    assert manifest_a.dataset_version == "v0.1.0"
    assert manifest_a.master_seed == 123
    assert manifest_a.num_templates_total == 8
    assert manifest_a.num_cases_total == 24
    assert manifest_a.hard_cases_count == round(24 * 0.10)

    # Exact snapshot list determinism
    assert [s.snapshot_id for s in snapshots_a] == [s.snapshot_id for s in snapshots_b]
    assert snapshots_a == snapshots_b

    # Verify save_dataset and load_dataset round-trip
    saved_paths = save_dataset(snapshots_a, manifest_a, tmp_path / "dataset_out")
    assert saved_paths["manifest_path"].exists()
    assert saved_paths["snapshots_path"].exists()

    loaded_snapshots, loaded_manifest = DatasetGenerator.load_dataset(
        tmp_path / "dataset_out"
    )
    assert loaded_manifest == manifest_a
    assert loaded_snapshots == snapshots_a

