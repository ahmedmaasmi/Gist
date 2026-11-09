# backend/tests/test_api.py
"""PRD 12-13 and 5.2: the Mode 1 API — a full game, T3 isolation (contracts + canaries), idempotency, validation."""
import types
import typing
import warnings

import pytest
from pydantic import BaseModel

from app.api import schemas
from app.domain.character import (
    Character,
    CharacterSecret,
    CharacterTraits,
    RelationshipEdge,
    RelationshipGraph,
)
from app.domain.tiers import T2CharacterKnowledge, T3Canonical
from app.domain.world import CanonicalEvent, LieAnnotation

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app

HIDDEN_TYPES = {T3Canonical, CanonicalEvent, LieAnnotation, RelationshipGraph, RelationshipEdge, Character,
                CharacterSecret, CharacterTraits, T2CharacterKnowledge}
HIDDEN_FIELDS = {"culprit_id", "canaries", "lie_annotations", "canonical_events", "relationship_graph",
                 "solution_summary", "ground_truth_facts", "is_crime_linked"}


def _reachable(model) -> tuple[set, set]:
    seen, names = set(), set()

    def visit(tp):
        if typing.get_origin(tp) is not None or isinstance(tp, types.UnionType):
            for a in typing.get_args(tp):
                visit(a)
        elif isinstance(tp, type) and issubclass(tp, BaseModel) and tp not in seen:
            seen.add(tp)
            for n, f in tp.model_fields.items():
                names.add(n)
                visit(f.annotation)

    visit(model)
    return seen, names


@pytest.mark.parametrize("model", [schemas.CaseSummary, schemas.SessionCreated, schemas.SessionView, schemas.VerdictView])
def test_responses_before_the_verdict_cannot_hold_hidden_data(model):
    reachable, names = _reachable(model)
    assert not reachable & HIDDEN_TYPES
    assert not names & HIDDEN_FIELDS


@pytest.fixture(scope="module")
def client():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return TestClient(app)


def _play(client, role: str):
    """Plays a full game, answering every question for you, and returns all response bodies and the session."""
    bodies = []
    cases = client.get("/cases")
    bodies.append(cases.text)
    case_id = cases.json()[0]["case_id"]
    created = client.post("/sessions", json={"case_id": case_id, "role": role})
    assert created.status_code == 201
    bodies.append(created.text)
    sid = created.json()["session"]["session_id"]
    you = created.json()["you"]
    for _ in range(12):
        r = client.post(f"/sessions/{sid}/next-question")
        bodies.append(r.text)
        if r.status_code == 409:
            break
        if r.json()["status"] == "awaiting_your_answer":
            a = client.post(f"/sessions/{sid}/claims", json={"location_id": you["where_you_really_were"][0]["location_id"]})
            assert a.status_code == 200
            bodies.append(a.text)
    bodies.append(client.get(f"/sessions/{sid}").text)
    bodies.append(client.get(f"/sessions/{sid}/ranking").text)
    bodies.append(client.post(f"/sessions/{sid}/verdict").text)
    return bodies, sid


@pytest.mark.parametrize("role", ["culprit", "innocent"])
def test_full_game_never_leaks_a_canary_or_the_culprit_before_results(client, role):
    bodies, sid = _play(client, role)
    session = client.app.state.game.get(sid)
    canaries = session.bundle.t3_canonical.canary_set()
    for body in bodies:
        assert "CANARY_T3_" not in body and not any(c in body for c in canaries)
        assert "culprit_id" not in body
    results = client.get(f"/sessions/{sid}/results")
    assert results.status_code == 200 and "CANARY_T3_" not in results.text
    assert results.json()["culprit_id"] == session.bundle.t3_canonical.culprit_id
    assert results.json()["your_role"] == role


def test_results_are_locked_until_the_verdict(client):
    case_id = client.get("/cases").json()[1]["case_id"]
    sid = client.post("/sessions", json={"case_id": case_id, "role": "innocent"}).json()["session"]["session_id"]
    assert client.get(f"/sessions/{sid}/results").status_code == 409


def test_idempotency_key_prevents_double_actions(client):
    case_id = client.get("/cases").json()[2]["case_id"]
    sid = client.post("/sessions", json={"case_id": case_id, "role": "innocent"}).json()["session"]["session_id"]
    first = client.post(f"/sessions/{sid}/next-question", headers={"Idempotency-Key": "k1"}).json()
    again = client.post(f"/sessions/{sid}/next-question", headers={"Idempotency-Key": "k1"}).json()
    assert first == again
    assert len(client.get(f"/sessions/{sid}").json()["detective_log"]) == 1


def test_player_input_is_validated_and_never_auto_verified(client):
    case_id = client.get("/cases").json()[0]["case_id"]
    sid = client.post("/sessions", json={"case_id": case_id, "role": "culprit"}).json()["session"]["session_id"]
    assert client.post(f"/sessions/{sid}/claims", json={"location_id": "loc_study"}).status_code == 409  # no question yet
    for _ in range(8):
        v = client.post(f"/sessions/{sid}/next-question").json()
        if v["status"] == "awaiting_your_answer":
            break
    else:
        pytest.skip("the detective never asked you in this case")
    assert client.post(f"/sessions/{sid}/claims", json={"location_id": "loc_moon"}).status_code == 422
    assert client.post(f"/sessions/{sid}/claims", json={"free_text": "x" * 501, "dont_remember": True}).status_code == 422
    ok = client.post(f"/sessions/{sid}/claims", json={"dont_remember": True, "free_text": "I really can't recall"}).json()
    mine = [c for c in ok["claims"] if c["speaker_id"] == ok["your_character_id"] and c["turn"] >= 1]
    assert mine[-1]["status"] == "UNVERIFIED" and mine[-1]["provenance"] == "SELF_REPORT"  # MD-04


def test_brief_contains_only_your_own_knowledge(client):
    case_id = client.get("/cases").json()[0]["case_id"]
    created = client.post("/sessions", json={"case_id": case_id, "role": "innocent"}).json()
    session = client.app.state.game.get(created["session"]["session_id"])
    others = [
        s.description
        for cid, pack in session.bundle.t2_knowledge.items()
        if cid != session.player_id and pack.character
        for s in pack.character.secrets
    ]
    assert not set(created["you"]["your_secrets"]) & set(others)
