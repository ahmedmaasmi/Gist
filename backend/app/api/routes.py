# backend/app/api/routes.py
"""
PRD 12 endpoints for Mode 1 (the Machine Detective). Mutating endpoints accept an `Idempotency-Key` header:
a repeated request with the same key returns the stored response instead of acting twice (PRD 13).
"""
from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.game import Game, GameError, Session
from app.api.schemas import (
    CaseSummary,
    ClaimRequest,
    CreateSessionRequest,
    PlayerBrief,
    ResultsView,
    SessionCreated,
    SessionView,
    VerdictView,
)
from app.api.views import case_summary, player_brief, results_view, session_view, verdict_view
from app.ml.ranker import RankingResult

router = APIRouter()


def _game(request: Request) -> Game:
    if getattr(request.app.state, "game", None) is None:
        request.app.state.game = Game()
    return request.app.state.game


def _session(request: Request, session_id: str) -> Session:
    try:
        return _game(request).get(session_id)
    except KeyError:
        raise HTTPException(404, "Unknown session") from None


def _idempotent(session: Session, endpoint: str, key: str | None, act: Callable[[], dict]) -> dict:
    if key and (endpoint, key) in session.idempotency:
        return session.idempotency[(endpoint, key)]
    try:
        result = act()
    except GameError as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    if key:
        session.idempotency[(endpoint, key)] = result
    return result


@router.get("/cases", response_model=list[CaseSummary])
def list_cases(request: Request) -> list[CaseSummary]:
    return [case_summary(b) for b in _game(request).catalogue.cases.values()]


@router.post("/sessions", response_model=SessionCreated, status_code=201)
def create_session(body: CreateSessionRequest, request: Request) -> SessionCreated:
    try:
        session = _game(request).create_session(body.case_id, body.role)
    except KeyError:
        raise HTTPException(404, "Unknown case") from None
    return SessionCreated(session=session_view(session), case=case_summary(session.bundle), you=player_brief(session))


@router.get("/sessions/{session_id}", response_model=SessionView)
def get_session(session_id: str, request: Request) -> SessionView:
    return session_view(_session(request, session_id))


@router.get("/sessions/{session_id}/you", response_model=PlayerBrief)
def get_brief(session_id: str, request: Request) -> PlayerBrief:
    """Your own character brief again (e.g. after a page reload)."""
    return player_brief(_session(request, session_id))


@router.get("/sessions/{session_id}/case", response_model=CaseSummary)
def get_case(session_id: str, request: Request) -> CaseSummary:
    return case_summary(_session(request, session_id).bundle)


@router.get("/sessions/{session_id}/ranking", response_model=RankingResult)
def get_ranking(session_id: str, request: Request) -> RankingResult:
    return _session(request, session_id).ranking


@router.get("/sessions/{session_id}/counterfactual", response_model=dict[str, float])
def counterfactual(session_id: str, evidence_id: str, request: Request) -> dict[str, float]:
    """MD-08: how each suspect's probability would change without one piece of evidence."""
    s = _session(request, session_id)
    return _game(request).ranker.counterfactual(s.bundle.t0_public, s.t1, s.bundle.setting, evidence_id)


@router.post("/sessions/{session_id}/next-question", response_model=SessionView)
def next_question(session_id: str, request: Request, idempotency_key: str | None = Header(default=None)):
    """The detective takes its next action (asks you, asks a scripted suspect, or requests records)."""
    s = _session(request, session_id)
    return _idempotent(s, "next-question", idempotency_key,
                       lambda: session_view(_step(request, s)).model_dump())


def _step(request: Request, s: Session) -> Session:
    _game(request).step(s)
    return s


@router.post("/sessions/{session_id}/claims", response_model=SessionView)
def answer(session_id: str, body: ClaimRequest, request: Request, idempotency_key: str | None = Header(default=None)):
    s = _session(request, session_id)

    def act() -> dict:
        _game(request).answer(s, body.location_id, body.dont_remember, body.observed_character_ids,
                              body.has_corroboration, body.free_text)
        return session_view(s).model_dump()

    return _idempotent(s, "claims", idempotency_key, act)


@router.post("/sessions/{session_id}/verdict", response_model=VerdictView)
def verdict(session_id: str, request: Request, idempotency_key: str | None = Header(default=None)):
    s = _session(request, session_id)

    def act() -> dict:
        _game(request).give_verdict(s)
        return verdict_view(s).model_dump()

    return _idempotent(s, "verdict", idempotency_key, act)


@router.get("/sessions/{session_id}/results", response_model=ResultsView)
def results(session_id: str, request: Request) -> ResultsView:
    s = _session(request, session_id)
    if s.verdict is None:
        raise HTTPException(409, "Results are only available after the verdict.")
    return results_view(s)
