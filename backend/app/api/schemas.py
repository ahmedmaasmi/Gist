# backend/app/api/schemas.py
"""
API request and response models (PRD 12). Response models are built ONLY from T0/T1 data, the player's own
T2 brief, and (after a verdict) a canary-stripped solution. tests/test_api.py walks every response model to
prove no T3 type can be placed in them, and scans every response of a full game for canary tokens.
"""
from pydantic import BaseModel, Field

from app.ml.ranker import ESTIMATE_LABEL, RankingResult


class LocationView(BaseModel):
    location_id: str
    name: str
    restricted: bool
    x: float | None = None
    y: float | None = None


class CharacterView(BaseModel):
    character_id: str
    name: str
    occupation: str


class CaseSummary(BaseModel):
    case_id: str
    title: str
    map_name: str
    synopsis: str
    victim: CharacterView
    suspects: list[CharacterView]
    locations: list[LocationView]
    crime_location_id: str
    crime_window_start: int
    crime_window_end: int
    role_variants: list[str] = Field(default_factory=lambda: ["culprit", "innocent"])


class CreateSessionRequest(BaseModel):
    case_id: str
    role: str = Field("innocent", pattern="^(culprit|innocent)$")


class TimelineEntry(BaseModel):
    minute: int
    location_id: str


class PlayerBrief(BaseModel):
    """Your own character's knowledge (your T2): what you did, what you hide, what you already told the police."""

    character: CharacterView
    role: str
    you_are_the_culprit: bool
    where_you_really_were: list[TimelineEntry]
    your_secrets: list[str]
    your_statement_so_far: str | None


class FactView(BaseModel):
    fact_id: str
    description: str
    subject_id: str | None
    location_id: str | None
    minute: int | None
    category: str
    provenance: str
    reliability: float
    status: str


class ClaimView(BaseModel):
    claim_id: str
    speaker_id: str
    location_id: str | None
    minute_start: int | None
    minute_end: int | None
    observed_character_ids: list[str]
    free_text: str | None
    provenance: str
    status: str
    turn: int


class ContradictionView(BaseModel):
    flag_id: str
    type: str
    suspect_id: str
    claim_id: str
    source_ids: list[str]
    explanation: str


class DisagreementView(BaseModel):
    disagreement_id: str
    suspect_ids: list[str]
    claim_ids: list[str]
    explanation: str


class QuestionView(BaseModel):
    kind: str
    suspect_id: str
    minute: int | None
    text: str
    for_you: bool


class DetectiveAction(BaseModel):
    """MD-03: what the detective did, and the alternatives it considered with their expected gains."""

    turn: int
    action: str
    outcome: str | None
    alternatives: list[tuple[str, float]] = Field(default_factory=list)


class PredictionLogEntry(BaseModel):
    """MD-02: every prediction with the model and feature-spec versions that produced it."""

    turn: int
    model_version: str
    feature_spec_version: str
    leading_suspect_id: str | None
    probabilities: dict[str, float]


class SessionView(BaseModel):
    session_id: str
    case_id: str
    your_character_id: str
    turn: int
    budget: int
    status: str  # investigating | awaiting_your_answer | ready_for_verdict | verdict_given
    pending_question: QuestionView | None
    facts: list[FactView]
    claims: list[ClaimView]
    contradictions: list[ContradictionView]
    disagreements: list[DisagreementView]
    ranking: RankingResult
    previous_ranking: dict[str, float] | None
    detective_log: list[DetectiveAction]
    prediction_log: list[PredictionLogEntry]


class SessionCreated(BaseModel):
    session: SessionView
    case: CaseSummary
    you: PlayerBrief


class ClaimRequest(BaseModel):
    """The claim builder (PRD 6.2): structured slots; free text is stored but never parsed in v0.1."""

    location_id: str | None = None
    dont_remember: bool = False
    observed_character_ids: list[str] = Field(default_factory=list, max_length=6)
    has_corroboration: bool = False
    free_text: str | None = Field(default=None, max_length=500)


class EvidenceItem(BaseModel):
    evidence_id: str
    text: str


class VerdictView(BaseModel):
    """MD-07: leading hypothesis, evidence, contradictions, alternatives and uncertainty, labelled as an estimate."""

    label: str = ESTIMATE_LABEL
    abstained: bool
    abstain_reason: str | None
    leading_suspect_id: str | None
    leading_probability: float | None
    supporting_evidence: list[EvidenceItem]
    contradictions: list[ContradictionView]
    alternatives: dict[str, float]
    model_version: str


class LieView(BaseModel):
    suspect_id: str
    kind: str
    note: str


class ResultsView(BaseModel):
    """Only after a verdict (PRD 5.2: the results endpoint may read the solution). Canary tokens stripped."""

    culprit_id: str
    culprit_name: str
    solution: str
    machine_verdict: VerdictView
    machine_was_right: bool | None
    your_role: str
    lies: list[LieView]
