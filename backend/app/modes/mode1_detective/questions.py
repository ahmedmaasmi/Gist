# backend/app/modes/mode1_detective/questions.py
"""
PRD 6.2 / 6.4.D: slot-based question bank. Every action concerns one suspect:

  ask(s, t)   "Where were you at HH:MM?" for t = start, middle and end of the (public) crime window
  check(s)    "Request the records about s": reveals s's not-yet-discovered records

Built only from T0 (suspect list and crime window), so the bank never depends on hidden data.
"""
from dataclasses import dataclass

from app.domain.tiers import T0Public

ASK = "ask"
CHECK = "check"


@dataclass(frozen=True, order=True)
class Action:
    kind: str
    suspect_id: str
    minute: int | None = None  # for ASK: the time asked about

    def label(self) -> str:
        if self.kind == CHECK:
            return f"check records of {self.suspect_id}"
        return f"ask {self.suspect_id}: where were you at {self.minute // 60:02d}:{self.minute % 60:02d}?"


def window_slots(t0: T0Public, tick: int = 10) -> list[int]:
    """Start, middle (rounded to a tick) and end of the public crime window."""
    w = t0.crime_window
    middle = w.start_min + ((w.end_min - w.start_min) // 2 // tick) * tick
    return sorted({w.start_min, middle, w.end_min})


def build_question_bank(t0: T0Public) -> list[Action]:
    slots = window_slots(t0)
    bank = [Action(ASK, s, t) for s in t0.suspect_ids for t in slots]
    bank += [Action(CHECK, s) for s in t0.suspect_ids]
    return bank
