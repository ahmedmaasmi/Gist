# backend/app/modes/mode1_detective/episode.py
"""
PRD 6.3 gameplay loop, simulated: the policy picks an action, the (simulated) player answers or records are
revealed, the consistency engine checks the new claim, and the ranker produces a new distribution.
"""
import random
from dataclasses import dataclass, field

from app.domain.simulation import SimulatedCaseBundle
from app.ml.ranker import Ranker
from app.modes.mode1_detective.interview import START_FRACTION, apply_action, initial_state
from app.modes.mode1_detective.players import behaviours
from app.modes.mode1_detective.questions import build_question_bank


@dataclass
class EpisodeResult:
    case_id: str
    culprit_id: str
    correct_by_step: list[bool]  # leading suspect correct after 0..budget actions
    actions: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    decision_logs: list[list[tuple[str, float]]] = field(default_factory=list)  # MD-03

    @property
    def reach_and_hold(self) -> int:
        """Fewest actions after which the leading suspect is correct and stays correct (budget+1 if never)."""
        k = len(self.correct_by_step)
        while k > 0 and self.correct_by_step[k - 1]:
            k -= 1
        return k if self.correct_by_step[-1] else len(self.correct_by_step)


def run_episode(
    bundle: SimulatedCaseBundle,
    policy,
    population: str,
    ranker: Ranker,
    budget: int = 8,
    seed: int = 0,
    start_fraction: float = START_FRACTION,
) -> EpisodeResult:
    # Separate random streams: the players' (evasion) and the policy's (random choices), so that comparing
    # policies on the same case and seed is as paired as possible.
    player_rng, policy_rng = random.Random(seed), random.Random(seed + 1_000_003)
    who = behaviours(bundle, population)
    t0, t1 = bundle.t0_public, initial_state(bundle, start_fraction)
    remaining = build_question_bank(t0)
    culprit = bundle.t3_canonical.culprit_id

    def leader_correct(probs: dict[str, float]) -> bool:
        best = max(probs.values())
        return [s for s, p in probs.items() if p == best] == [culprit]

    probs = ranker.rank(t0, t1, bundle.setting).probabilities
    result = EpisodeResult(bundle.config.case_id, culprit, [leader_correct(probs)])
    for turn in range(1, budget + 1):
        action, considered = policy.choose(t0, t1, probs, remaining, policy_rng)
        remaining = [a for a in remaining if a != action]
        t1, outcome = apply_action(bundle, t1, action, who, player_rng, turn)
        probs = ranker.rank(t0, t1, bundle.setting).probabilities
        result.actions.append(action.label())
        result.outcomes.append(outcome)
        result.decision_logs.append(considered)
        result.correct_by_step.append(leader_correct(probs))
    return result
