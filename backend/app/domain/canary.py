# backend/app/domain/canary.py
"""
PRD Section 5.2: Each T3 text field contains a unique canary token; automated tests assert
that no canary ever appears in an API response, prompt or log.

A canary is a random-looking marker string planted inside secret data. If it ever shows up
in a public payload, some code path copied T3 text where it must not. Canaries are derived
by hashing (case_id, seed, field_path), so the same simulation always produces the same
canaries (CH-03 determinism) while every field of every case gets a different one.
"""
import hashlib
import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

CANARY_PREFIX = "CANARY_T3_"


def make_canary(case_id: str, seed: int, field_path: str) -> str:
    """Deterministic, unique canary for one T3 field of one case."""
    digest = hashlib.sha256(f"{case_id}|{seed}|{field_path}".encode()).hexdigest()[:12]
    return f"{CANARY_PREFIX}{digest}"


def stamp(text: str, canary: str) -> str:
    """Prefix text with its canary. Idempotent, so re-validating a T3 record is safe."""
    if canary in text:
        return text
    return f"[{canary}] {text}" if text else f"[{canary}]"


def _serialise(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, BaseModel):
        return payload.model_dump_json()
    return json.dumps(payload, default=str)


def find_canaries(payload: Any, canaries: Iterable[str] = ()) -> list[str]:
    """
    Returns every canary found in the payload (a string, Pydantic model, or JSON-able object).
    Also catches the generic prefix, so a canary from a *different* case is detected too.
    """
    text = _serialise(payload)
    found = [c for c in canaries if c in text]
    if CANARY_PREFIX in text and not found:
        found.append(CANARY_PREFIX)
    return found


def assert_no_canary(payload: Any, canaries: Iterable[str] = (), where: str = "payload") -> None:
    """Raises AssertionError if any T3 canary appears in the payload."""
    leaked = find_canaries(payload, canaries)
    if leaked:
        raise AssertionError(f"T3 canary leaked into {where}: {leaked}")
