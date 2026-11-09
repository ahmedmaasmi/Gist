# backend/tests/test_case_variety.py
"""Step 5a: per-case variables and the famous-names pool."""
import json
from collections import Counter

from app.engine.templates import (
    CASE_VARIABLE_RANGES,
    NAMES_PATH,
    get_template,
    load_all_templates,
    load_name_pool,
    sample_case_setup_from_template,
)


def _setups(n_seeds=8):
    for template_id in sorted(load_all_templates()):
        for seed in range(n_seeds):
            yield sample_case_setup_from_template(template=get_template(template_id), seed=seed)


def test_case_variables_stay_in_documented_ranges_and_actually_vary():
    seen = {k: set() for k in CASE_VARIABLE_RANGES}
    for setup in _setups():
        cfg = setup.config
        values = {
            "num_suspects": len(setup.characters) - 1,
            "murder_window_start_min": cfg.murder_window.start_min,
            "murder_window_length_min": cfg.murder_window.duration,
            "witness_noise_rate": cfg.witness_noise_rate,
            "record_drop_rate": cfg.record_drop_rate,
            "forensic_trace_rate": cfg.forensic_trace_rate,
            "guilty_lie_rate": cfg.guilty_lie_rate,
            "innocent_lie_rate": cfg.innocent_lie_rate,
        }
        for name, value in values.items():
            low, high = CASE_VARIABLE_RANGES[name]
            assert low <= value <= high, (name, value)
            seen[name].add(value)
    for name in seen:
        if name != "travel_time_factor":
            assert len(seen[name]) > 1, f"{name} never varies"


def test_victim_reaches_the_scene_before_the_window():
    for setup in _setups(3):
        victim = next(c for c in setup.characters if c.character_id == setup.config.victim_id)
        last = victim.schedule[-1]
        assert last.planned_location_id == setup.config.crime_location_id
        assert last.time_interval.start_min <= setup.config.murder_window.start_min


def test_name_pool_policy():
    doc = json.loads(NAMES_PATH.read_text(encoding="utf-8"))
    names = [e["name"] for e in doc["names"]]
    assert len(names) == len(set(names)) >= 7  # enough for a victim + 6 suspects
    for entry in doc["names"]:
        assert entry["kind"] in {"historical", "legend", "fictional"}
        assert entry["source"].strip()
    # Still-copyrighted characters are excluded
    assert not {"Hercule Poirot", "Miss Marple", "Jane Marple"} & set(names)


def test_names_are_drawn_from_the_pool_and_do_not_predict_guilt():
    """Every famous name should be the culprit about as often as chance allows (PRD 7A.1)."""
    pool = set(load_name_pool())
    appearances, guilty = Counter(), Counter()
    for setup in _setups(12):
        bundle = setup.simulate()
        names = {c.character_id: c.name for c in setup.characters}
        assert set(names.values()) <= pool
        for sid in bundle.t0_public.suspect_ids:
            appearances[names[sid]] += 1
        guilty[names[bundle.t3_canonical.culprit_id]] += 1
    overall = sum(guilty.values()) / sum(appearances.values())
    for name, n in appearances.items():
        if n >= 20:
            assert guilty[name] / n < overall + 0.25, (name, guilty[name], n)
