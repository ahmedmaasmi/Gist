# backend/app/modes/mode1_detective/policies.py
"""
PRD 6.4.D question-selection policies. Each returns (chosen action, alternatives considered with scores),
so every choice can be logged with its expected gain (MD-03).

  random        uniform over unused questions
  fixed_order   a naive script: ask everyone about the middle of the window, then the start, then the end,
                then request records, suspects in listed order
  top_two       focus on the two current favourites: records first, then the middle slot, alternating
  entropy       maximise the expected drop in entropy of the suspect distribution, using an answer-outcome
                model P(outcome | suspect is culprit / innocent, question type) estimated by simulation on
                training templates (PRD 6.4.D, 9.3)
"""
import json
import math
import random
from pathlib import Path

from app.modes.mode1_detective.questions import ASK, CHECK, Action

Considered = list[tuple[str, float]]


class RandomPolicy:
    name = "random"

    def choose(self, t0, t1, probs, remaining: list[Action], rng: random.Random) -> tuple[Action, Considered]:
        return rng.choice(remaining), []


class FixedOrderPolicy:
    name = "fixed_order"

    def choose(self, t0, t1, probs, remaining: list[Action], rng: random.Random) -> tuple[Action, Considered]:
        w = t0.crime_window
        mid = w.start_min + ((w.end_min - w.start_min) // 2 // 10) * 10
        order = {mid: 0, w.start_min: 1, w.end_min: 2}
        position = {s: i for i, s in enumerate(t0.suspect_ids)}

        def key(a: Action):
            return (3, position[a.suspect_id], 0) if a.kind == CHECK else (order[a.minute], position[a.suspect_id], 0)

        return min(remaining, key=key), []


class TopTwoPolicy:
    name = "top_two"

    def choose(self, t0, t1, probs, remaining: list[Action], rng: random.Random) -> tuple[Action, Considered]:
        ranked = sorted(probs, key=lambda s: (-probs[s], s))
        w = t0.crime_window
        mid = w.start_min + ((w.end_min - w.start_min) // 2 // 10) * 10
        for kind, minute in ((CHECK, None), (ASK, mid), (ASK, w.start_min), (ASK, w.end_min)):
            for s in ranked[:2]:
                a = Action(kind, s, minute)
                if a in remaining:
                    return a, [(a.label(), probs[s])]
        return min(remaining), []  # both favourites exhausted: fall back to a fixed choice


def entropy(probs: dict[str, float]) -> float:
    return -sum(p * math.log(p) for p in probs.values() if p > 0)


class OutcomeModel:
    """P(outcome | role, question type), with add-one smoothing; estimated on training templates only."""

    def __init__(self, counts: dict[str, dict[str, dict[str, int]]]):
        self.counts = counts

    def likelihood(self, kind: str, role: str, outcome: str) -> float:
        table = self.counts[kind][role]
        return (table.get(outcome, 0) + 1) / (sum(table.values()) + len(table))

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path) -> "OutcomeModel":
        return cls(json.loads(path.read_text(encoding="utf-8")))


class EntropyPolicy:
    name = "entropy"

    def __init__(self, outcome_model: OutcomeModel):
        self.model = outcome_model

    def expected_entropy(self, probs: dict[str, float], action: Action) -> float:
        """E over outcomes of the entropy after a Bayesian update of `probs` with the outcome likelihoods."""
        s = action.suspect_id
        total = 0.0
        for outcome in self.model.counts[action.kind]["culprit"]:
            l_c = self.model.likelihood(action.kind, "culprit", outcome)
            l_i = self.model.likelihood(action.kind, "innocent", outcome)
            joint = {x: p * (l_c if x == s else l_i) for x, p in probs.items()}
            p_outcome = sum(joint.values())
            total += p_outcome * entropy({x: v / p_outcome for x, v in joint.items()})
        return total

    def choose(self, t0, t1, probs, remaining: list[Action], rng: random.Random) -> tuple[Action, Considered]:
        h_now = entropy(probs)
        gains = sorted(((h_now - self.expected_entropy(probs, a), a) for a in remaining), key=lambda g: (-g[0], g[1]))
        considered = [(a.label(), round(g, 4)) for g, a in gains[:5]]
        return gains[0][1], considered
