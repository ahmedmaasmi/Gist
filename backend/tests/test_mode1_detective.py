# backend/tests/test_mode1_detective.py
"""Step 9: question bank, simulated players, policies and the episode loop."""
import random

import pytest

from app.engine.dataset_generator import DatasetGenerator
from app.engine.templates import CASE_VARIABLE_RANGES, get_template
from app.ml.ranker import Ranker
from app.modes.mode1_detective.episode import EpisodeResult, run_episode
from app.modes.mode1_detective.interview import apply_action, initial_state
from app.modes.mode1_detective.players import (
    Behaviour,
    answer_location,
    behaviours,
    cover_story_location,
    true_location,
)
from app.modes.mode1_detective.policies import (
    EntropyPolicy,
    FixedOrderPolicy,
    OutcomeModel,
    RandomPolicy,
    TopTwoPolicy,
    entropy,
)
from app.modes.mode1_detective.questions import ASK, CHECK, Action, build_question_bank


@pytest.fixture(scope="module")
def bundle():
    b, _ = DatasetGenerator._generate_validated_case(get_template("manor"), "case_t", 4242, CASE_VARIABLE_RANGES)
    return b


def test_question_bank_uses_only_public_data(bundle):
    bank = build_question_bank(bundle.t0_public)
    n = len(bundle.t0_public.suspect_ids)
    assert len(bank) == 4 * n and len(set(bank)) == len(bank)
    w = bundle.t0_public.crime_window
    assert all(a.kind == CHECK or w.contains(a.minute) for a in bank)


def test_players_answer_from_the_truth_or_their_story(bundle):
    culprit = bundle.t3_canonical.culprit_id
    honest, liar = Behaviour(False, 0.0), Behaviour(True, 0.0)
    minute = bundle.t0_public.crime_window.start_min
    rng = random.Random(0)
    assert answer_location(bundle, honest, culprit, minute, rng) == true_location(bundle, culprit, minute)
    assert answer_location(bundle, liar, culprit, minute, rng) == cover_story_location(bundle, culprit)
    assert answer_location(bundle, Behaviour(False, 1.0), culprit, minute, rng) is None  # always evasive
    assert behaviours(bundle, "honest_innocents")[culprit].keeps_cover_story


def test_actions_change_the_state_as_expected(bundle):
    t1 = initial_state(bundle)
    who = behaviours(bundle, "honest_innocents")
    s = bundle.t0_public.suspect_ids[0]
    after, outcome = apply_action(bundle, t1, Action(CHECK, s), who, random.Random(0), 1)
    assert outcome in {"scene_record", "other_record", "nothing"}
    assert {f.fact_id for f in t1.discovered_facts} <= {f.fact_id for f in after.discovered_facts}
    minute = bundle.t0_public.crime_window.start_min
    after, outcome = apply_action(bundle, t1, Action(ASK, s, minute), who, random.Random(0), 1)
    assert outcome in {"consistent", "refuted", "self_contradiction"}
    assert len(after.recorded_claims) == len(t1.recorded_claims) + 1


def test_entropy_policy_prefers_informative_questions():
    model = OutcomeModel({
        "ask": {"culprit": {"consistent": 50, "refuted": 50}, "innocent": {"consistent": 50, "refuted": 50}},
        "check": {"culprit": {"scene_record": 90, "nothing": 10}, "innocent": {"scene_record": 10, "nothing": 90}},
    })
    probs = {"a": 0.5, "b": 0.5}
    remaining = [Action(ASK, "a", 1260), Action(CHECK, "a")]
    action, considered = EntropyPolicy(model).choose(None, None, probs, remaining, random.Random(0))
    assert action == Action(CHECK, "a") and considered[0][1] > considered[1][1]  # logged gains (MD-03)
    assert entropy({"a": 1.0}) == 0.0


def test_episode_runs_with_every_policy_and_logs(bundle):
    ranker = Ranker.load()
    model = OutcomeModel({
        "ask": {r: {"consistent": 1, "refuted": 1, "self_contradiction": 1, "evasive": 1} for r in ("culprit", "innocent")},
        "check": {r: {"scene_record": 1, "other_record": 1, "nothing": 1} for r in ("culprit", "innocent")},
    })
    for policy in (RandomPolicy(), FixedOrderPolicy(), TopTwoPolicy(), EntropyPolicy(model)):
        result = run_episode(bundle, policy, "mixed", ranker, budget=4, seed=1)
        assert len(result.correct_by_step) == 5 and len(result.actions) == 4
        assert len(set(result.actions)) == 4  # each question at most once


def test_reach_and_hold():
    def res(c):
        return EpisodeResult("c", "x", c)

    assert res([False, True, True]).reach_and_hold == 1
    assert res([True, False, True]).reach_and_hold == 2
    assert res([True, True]).reach_and_hold == 0
    assert res([True, False]).reach_and_hold == 2  # never held: budget + 1
