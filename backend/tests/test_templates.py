# backend/tests/test_templates.py
import pytest
from pydantic import ValidationError

from app.domain.enums import InteractionType
from app.domain.setting import Location, SettingTemplate
from app.engine.simulator import SocialSimulator
from app.engine.templates import (
    TemplateRegistry,
    generate_valid_case,
    get_template,
    get_templates_by_split,
    load_all_templates,
    sample_case_setup_from_template,
)

EXPECTED_TEMPLATE_IDS = {
    "manor",
    "train",
    "office",
    "clinic",
    "gallery",
    "yacht",
    "warehouse",
    "lodge",
    "hotel",
    "theatre",
    "abbey",
    "college",
}
HELD_OUT_TEMPLATE_IDS = {"train", "lodge", "abbey"}


def test_all_templates_load_and_validate() -> None:
    """
    Verifies all 12 JSON templates in `data/templates/` load cleanly,
    pass SettingTemplate Pydantic validation, respect CL-06 location caps (3..8),
    and have complete, non-negative travel matrices and valid default_crime_location_ids.
    """
    templates = load_all_templates(force_reload=True)
    assert set(templates.keys()) == EXPECTED_TEMPLATE_IDS
    assert len(templates) == 12

    for tpl_id, tpl in templates.items():
        assert tpl.template_id == tpl_id
        assert len(tpl.name) > 0
        assert len(tpl.description) > 0
        # CL-06: 3 <= len(locations) <= 8
        assert 3 <= len(tpl.locations) <= 8
        assert len(tpl.default_crime_location_ids) >= 1
        assert len(tpl.archetype_occupations) >= 5

        loc_ids = {loc.location_id for loc in tpl.locations}
        for crime_loc_id in tpl.default_crime_location_ids:
            assert crime_loc_id in loc_ids

        # Verify travel_matrix completeness and non-negativity
        for loc_a in loc_ids:
            assert loc_a in tpl.travel_matrix
            assert tpl.get_travel_time(loc_a, loc_a) == 0
            for loc_b in loc_ids:
                assert loc_b in tpl.travel_matrix[loc_a]
                travel_min = tpl.get_travel_time(loc_a, loc_b)
                assert travel_min >= 0
                if loc_a != loc_b:
                    assert travel_min > 0

        # Registry lookup by ID and prefixed ID
        assert get_template(tpl_id).template_id == tpl_id
        assert TemplateRegistry.get_template(f"tpl_{tpl_id}").template_id == tpl_id


def test_template_split_group_distribution() -> None:
    """
    PRD 8.4: 3 templates are held out entirely (never trained or tuned on); the other 9 are 'dev'
    templates whose cases are split train/val/test by case.
    """
    held_out_ids = {t.template_id for t in get_templates_by_split("test_held_out_template")}
    dev_ids = {t.template_id for t in get_templates_by_split("dev")}
    assert held_out_ids == HELD_OUT_TEMPLATE_IDS
    assert dev_ids == EXPECTED_TEMPLATE_IDS - HELD_OUT_TEMPLATE_IDS

    with pytest.raises(ValueError, match="Invalid split_group"):
        get_templates_by_split("invalid_split")


def test_cl06_server_side_size_caps_and_template_validation() -> None:
    """
    Task 4.3 (Requirement CL-06): Verifies server-side size caps on SettingTemplate
    (3 <= locations <= 8) and sample_case_setup_from_template (3 <= num_suspects <= 6).
    """
    # 1. SettingTemplate with 9 locations -> ValidationError (CL-06 max 8)
    nine_locs = [
        Location(location_id=f"loc_{i}", name=f"Room {i}", is_restricted=(i == 0))
        for i in range(9)
    ]
    nine_matrix = {
        f"loc_{i}": {f"loc_{j}": (0 if i == j else 5) for j in range(9)}
        for i in range(9)
    }
    with pytest.raises(ValidationError):
        SettingTemplate(
            template_id="tpl_too_large",
            name="Too Many Rooms",
            locations=nine_locs,
            travel_matrix=nine_matrix,
            default_crime_location_ids=["loc_0"],
        )

    # 2. SettingTemplate with 2 locations -> ValidationError (CL-06 min 3)
    two_locs = [
        Location(location_id="loc_0", name="Room 0", is_restricted=True),
        Location(location_id="loc_1", name="Room 1", is_restricted=False),
    ]
    two_matrix = {
        "loc_0": {"loc_0": 0, "loc_1": 5},
        "loc_1": {"loc_0": 5, "loc_1": 0},
    }
    with pytest.raises(ValidationError):
        SettingTemplate(
            template_id="tpl_too_small",
            name="Too Few Rooms",
            locations=two_locs,
            travel_matrix=two_matrix,
            default_crime_location_ids=["loc_0"],
        )

    # 3. SettingTemplate with unknown default_crime_location_ids -> ValidationError
    three_locs = [
        Location(location_id=f"loc_{i}", name=f"Room {i}", is_restricted=(i == 0))
        for i in range(3)
    ]
    three_matrix = {
        f"loc_{i}": {f"loc_{j}": (0 if i == j else 4) for j in range(3)}
        for i in range(3)
    }
    with pytest.raises(ValidationError, match="default_crime_location_ids contains unknown"):
        SettingTemplate(
            template_id="tpl_bad_crime_loc",
            name="Bad Crime Loc",
            locations=three_locs,
            travel_matrix=three_matrix,
            default_crime_location_ids=["loc_missing"],
        )

    # 4. SettingTemplate with incomplete travel_matrix -> ValidationError
    with pytest.raises(ValidationError, match="incomplete"):
        SettingTemplate(
            template_id="tpl_incomplete_matrix",
            name="Incomplete Matrix",
            locations=three_locs,
            travel_matrix={
                "loc_0": {"loc_1": 4},
                "loc_1": {"loc_0": 4, "loc_2": 4},
                "loc_2": {"loc_0": 4, "loc_1": 4},
            },
            default_crime_location_ids=["loc_0"],
        )

    # 5. sample_case_setup_from_template with num_suspects=2 or num_suspects=8 -> ValueError
    manor = get_template("manor")
    with pytest.raises(ValueError, match="CL-06 Violation"):
        sample_case_setup_from_template(manor, seed=42, num_suspects=2)

    with pytest.raises(ValueError, match="CL-06 Violation"):
        sample_case_setup_from_template(manor, seed=42, num_suspects=8)


@pytest.mark.parametrize("template_id", sorted(EXPECTED_TEMPLATE_IDS))
def test_end_to_end_template_simulation_and_solvability(template_id: str) -> None:
    """
    Task 4.4: For each of the 8 templates, sample a case setup with seed=42,
    run SocialSimulator + ObservationModel, and assert:
    - CaseSolvabilityValidator.validate_case returns is_valid=True
    - CH-04 check_ood() returns zero warnings for all sampled characters
    - Social interactions occur. They are probabilistic now (no scripted roles), so all three
      types are required across 20 seeds rather than in every single case.
    """
    template = get_template(template_id)
    setup = sample_case_setup_from_template(template, seed=42, num_suspects=4)

    # Verify 4 suspects + 1 victim = 5 characters
    assert len(setup.characters) == 5

    # Verify CH-04 OOD check returns zero warnings for every character
    for char in setup.characters:
        ood_warnings = char.traits.check_ood()
        assert ood_warnings == [], f"Unexpected OOD warnings for {char.character_id}: {ood_warnings}"

    # Run SocialSimulator + ObservationModel
    simulator = SocialSimulator(
        config=setup.config,
        setting=setup.setting,
        characters=setup.characters,
        relationship_graph=setup.relationship_graph,
    )
    simulator.simulate()

    # Check social interactions are generated across seeds
    interaction_types = {
        ev.interaction_type
        for seed in range(20)
        for ev in sample_case_setup_from_template(template, seed=seed).simulate().canonical_events
        if ev.event_kind == "INTERACTION" and ev.interaction_type is not None
    }
    assert InteractionType.ARGUE in interaction_types
    assert InteractionType.CONFIDE in interaction_types
    assert InteractionType.COVER_FOR in interaction_types

    # Validate solvability checks 1-3 (check 4 only labels difficulty for generated data)
    _, bundle, report = generate_valid_case(template, base_seed=42)
    assert report.is_valid is True, (
        f"Template '{template_id}' failed solvability validation on seed=42: "
        f"{report.failure_reasons}"
    )
    assert len(report.plausible_suspect_ids) >= 2
    assert len(report.red_herring_suspect_ids) >= 1
    assert bundle.t3_canonical.culprit_id in report.plausible_suspect_ids


def test_full_trait_range_and_variable_suspect_counts() -> None:
    """
    PRD 8.2 implementation note: training samples traits over the full editor range, so
    sampled traits reach both ends of [0, 1] and none is OOD. Variable suspect counts
    (3, 4, 5, 6) all simulate and validate cleanly via generate_valid_case.
    """
    train_tpl = get_template("train")

    # 1. Traits span the full range, and the CH-04 check (same range) never fires
    values = [
        getattr(char.traits, name)
        for seed in range(30)
        for char in sample_case_setup_from_template(train_tpl, seed=seed).characters
        for name in ("temper", "greed", "loyalty", "honesty", "composure", "secrecy")
    ]
    assert min(values) < 0.05 and max(values) > 0.95
    assert all(
        char.traits.check_ood() == []
        for char in sample_case_setup_from_template(train_tpl, seed=99).characters
    )

    # 2. Verify suspect counts 3..6 all produce valid cases
    for n_suspects in (3, 4, 5, 6):
        setup, bundle, report = generate_valid_case(
            template=train_tpl,
            base_seed=100 + n_suspects,
            num_suspects=n_suspects,
        )
        assert len(setup.characters) == n_suspects + 1
        assert len(bundle.t0_public.suspect_ids) == n_suspects
        assert report.is_valid is True


@pytest.mark.parametrize("template_id", sorted(EXPECTED_TEMPLATE_IDS))
def test_map_quality(template_id: str) -> None:
    """
    Every map is a proper floor plan: symmetric travel times of 1-15 minutes, no detour shorter
    than the direct route, 7-8 rooms, and every murder room has a neighbour within one tick
    (so a culprit can always reach it). Also holds for the per-case travel-time variation.
    """
    import random

    base = get_template(template_id)
    assert 7 <= len(base.locations) <= 8
    assert all(loc.x is not None and loc.y is not None for loc in base.locations)
    for tpl in (base, base.with_travel_variation(random.Random(0), 0.8, 1.2)):
        ids = [loc.location_id for loc in tpl.locations]
        t = tpl.travel_matrix
        for a in ids:
            for b in ids:
                assert t[a][b] == t[b][a]
                if a != b:
                    assert 1 <= t[a][b] <= 18  # <= 15 on the base map, x1.2 at most with variation
                for c in ids:
                    assert t[a][c] <= t[a][b] + t[b][c]
        if tpl is base:
            assert max(t[a][b] for a in ids for b in ids) <= 15
        for crime in tpl.default_crime_location_ids:
            assert min(t[crime][o] for o in ids if o != crime) <= 10

