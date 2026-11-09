# backend/app/api/game.py
"""
Mode 1 game logic behind the API (PRD 6.3): you play one suspect; the Machine Detective investigates.
The full case (incl. T3) stays inside `Session.bundle` on the server; only views built in `views.py` leave it.
"""
import json
import random
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cached_property
from pathlib import Path

from app.domain.simulation import SimulatedCaseBundle
from app.domain.tiers import T1Session
from app.domain.world import Claim, TimeInterval
from app.engine.dataset_generator import DatasetGenerator
from app.engine.templates import CASE_VARIABLE_RANGES, get_template
from app.ml.ranker import Ranker, RankingResult
from app.modes.mode1_detective.interview import apply_action, initial_state
from app.modes.mode1_detective.players import behaviours
from app.modes.mode1_detective.policies import EntropyPolicy, OutcomeModel
from app.modes.mode1_detective.questions import ASK, Action, build_question_bank

PLAYABLE_TEMPLATE = "manor"  # v0.1: one playable setting (PRD 14)
CATALOGUE_SIZE = 6
CATALOGUE_SEED = 7_000_000
DETECTIVE_BUDGET = 8
OUTCOME_MODEL_PATH = Path(__file__).resolve().parents[3] / "data" / "outcome_model.json"
CANARY_PATTERN = re.compile(r"\[?CANARY_T3_[0-9a-f]+\]?\s?")


class GameError(Exception):
    """A request that is valid HTTP but not allowed in the current game state (mapped to 409)."""


def strip_canaries(text: str) -> str:
    return CANARY_PATTERN.sub("", text)


class Catalogue:
    """Deterministic playable cases, generated once on first use."""

    @cached_property
    def cases(self) -> dict[str, SimulatedCaseBundle]:
        tpl = get_template(PLAYABLE_TEMPLATE)
        out = {}
        for i in range(CATALOGUE_SIZE):
            case_id = f"play_{PLAYABLE_TEMPLATE}_{i + 1:02d}"
            bundle, _ = DatasetGenerator._generate_validated_case(
                tpl, case_id, CATALOGUE_SEED + i * 100, CASE_VARIABLE_RANGES
            )
            out[case_id] = bundle
        return out

    def get(self, case_id: str) -> SimulatedCaseBundle:
        if case_id not in self.cases:
            raise KeyError(case_id)
        return self.cases[case_id]


@dataclass
class Session:
    session_id: str
    bundle: SimulatedCaseBundle
    player_id: str
    role: str
    t1: T1Session
    remaining: list[Action]
    turn: int = 0
    pending: Action | None = None
    verdict: dict | None = None
    ranking: RankingResult | None = None
    previous_probabilities: dict[str, float] | None = None
    detective_log: list[dict] = field(default_factory=list)
    prediction_log: list[dict] = field(default_factory=list)
    idempotency: dict[tuple[str, str], dict] = field(default_factory=dict)
    rng: random.Random = field(default_factory=random.Random)

    @property
    def status(self) -> str:
        if self.verdict is not None:
            return "verdict_given"
        if self.pending is not None:
            return "awaiting_your_answer"
        return "ready_for_verdict" if self.turn >= DETECTIVE_BUDGET else "investigating"


class Game:
    def __init__(self, ranker: Ranker | None = None, outcome_model: OutcomeModel | None = None):
        self.catalogue = Catalogue()
        self.ranker = ranker or Ranker.load()
        if outcome_model is None:
            counts = json.loads(OUTCOME_MODEL_PATH.read_text(encoding="utf-8"))["counts"]
            outcome_model = OutcomeModel(counts)
        self.policy = EntropyPolicy(outcome_model)
        self.sessions: dict[str, Session] = {}

    # --- sessions
    def create_session(self, case_id: str, role: str) -> Session:
        bundle = self.catalogue.get(case_id)
        culprit = bundle.t3_canonical.culprit_id
        rng = random.Random(f"{case_id}:{role}")
        innocents = [s for s in bundle.t0_public.suspect_ids if s != culprit]
        player = culprit if role == "culprit" else rng.choice(innocents)
        session = Session(
            session_id=secrets.token_urlsafe(12),
            bundle=bundle,
            player_id=player,
            role=role,
            t1=initial_state(bundle),
            remaining=build_question_bank(bundle.t0_public),
            rng=random.Random(f"{case_id}:{role}:play"),
        )
        self._rerank(session)
        self.sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            raise KeyError(session_id)
        return self.sessions[session_id]

    def _rerank(self, session: Session) -> None:
        if session.ranking is not None:
            session.previous_probabilities = session.ranking.probabilities
        session.ranking = self.ranker.rank(session.bundle.t0_public, session.t1, session.bundle.setting)
        session.prediction_log.append({
            "turn": session.turn,
            "model_version": session.ranking.model_version,
            "feature_spec_version": session.ranking.feature_spec_version,
            "leading_suspect_id": session.ranking.leading_suspect_id,
            "probabilities": session.ranking.probabilities,
        })

    # --- the detective's move
    def step(self, session: Session) -> None:
        if session.status == "verdict_given":
            raise GameError("The case is closed: a verdict has been given.")
        if session.pending is not None:
            raise GameError("The detective is waiting for your answer.")
        if session.turn >= DETECTIVE_BUDGET or not session.remaining:
            raise GameError("The detective has used its question budget; ask for the verdict.")
        action, considered = self.policy.choose(
            session.bundle.t0_public, session.t1, session.ranking.probabilities, session.remaining, session.rng
        )
        session.remaining = [a for a in session.remaining if a != action]
        entry = {"turn": session.turn + 1, "action": action.label(), "outcome": None, "alternatives": considered}
        session.detective_log.append(entry)
        if action.kind == ASK and action.suspect_id == session.player_id:
            session.pending = action  # a human answers this one
            return
        scripted = behaviours(session.bundle, "mixed")
        session.t1, entry["outcome"] = apply_action(
            session.bundle, session.t1, action, scripted, session.rng, session.turn + 1
        )
        session.turn += 1
        self._rerank(session)

    # --- your answer (claim builder)
    def answer(self, session: Session, location_id: str | None, dont_remember: bool, observed: list[str],
               has_corroboration: bool, free_text: str | None) -> None:
        if session.pending is None:
            raise GameError("There is no question waiting for you.")
        locations = {loc.location_id for loc in session.bundle.setting.locations}
        if not dont_remember and location_id not in locations:
            raise ValueError("location_id must be one of the map's rooms (or set dont_remember).")
        unknown = set(observed) - set(session.bundle.t0_public.suspect_ids) - {session.bundle.t0_public.victim_id}
        if unknown:
            raise ValueError(f"Unknown characters: {sorted(unknown)}")
        q = session.pending
        claim = Claim(
            claim_id=f"claim_{session.bundle.config.case_id}_{session.player_id}_q{session.turn + 1}",
            case_id=session.bundle.config.case_id,
            speaker_id=session.player_id,
            subject_id=session.player_id,
            turn_index=session.turn + 1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=session.bundle.config.end_min + session.turn + 1),
            claimed_location_id=None if dont_remember else location_id,
            claimed_time_interval=TimeInterval(start_min=q.minute, end_min=q.minute),
            observed_character_ids=sorted(set(observed) - {session.player_id}),
            has_corroboration_claim=has_corroboration,
            free_text=(free_text or "").strip() or None,
        )  # MD-04: SELF_REPORT and UNVERIFIED by default; never auto-verified
        session.t1 = session.t1.model_copy(update={"recorded_claims": [*session.t1.recorded_claims, claim]})
        session.detective_log[-1]["outcome"] = "answered by you" if not dont_remember else "you did not remember"
        session.pending = None
        session.turn += 1
        self._rerank(session)

    # --- verdict and results
    def give_verdict(self, session: Session) -> dict:
        if session.pending is not None:
            raise GameError("Answer the pending question before the verdict.")
        if session.verdict is None:
            session.verdict = {"ranking": session.ranking, "turn": session.turn}
        return session.verdict
