# backend/app/api/views.py
"""Builds response models from server-side state. The ONLY place server state is turned into client data."""
from app.api.game import Session, strip_canaries
from app.api.schemas import (
    CaseSummary,
    CharacterView,
    ClaimView,
    ContradictionView,
    DetectiveAction,
    DisagreementView,
    EvidenceItem,
    FactView,
    LieView,
    LocationView,
    PlayerBrief,
    PredictionLogEntry,
    QuestionView,
    ResultsView,
    SessionView,
    TimelineEntry,
    VerdictView,
)
from app.domain.simulation import SimulatedCaseBundle
from app.engine.consistency import StructuredConsistencyEngine


def _character(bundle: SimulatedCaseBundle, character_id: str) -> CharacterView:
    pack = bundle.t2_knowledge.get(character_id)
    c = pack.character if pack else None
    return CharacterView(character_id=character_id, name=c.name if c else character_id,
                         occupation=c.occupation if c else "")


def case_summary(bundle: SimulatedCaseBundle) -> CaseSummary:
    t0, setting = bundle.t0_public, bundle.setting
    rooms = {loc.location_id: loc.name for loc in setting.locations}
    w = t0.crime_window
    victim = _character(bundle, t0.victim_id)
    return CaseSummary(
        case_id=t0.case_id,
        title=f"Death at {setting.name}",
        map_name=setting.name,
        synopsis=(
            f"{victim.name} was found dead in {rooms[t0.crime_location_id]}. The murder happened between "
            f"{w.start_min // 60:02d}:{w.start_min % 60:02d} and {w.end_min // 60:02d}:{w.end_min % 60:02d}. "
            f"{len(t0.suspect_ids)} people were in the house."
        ),
        victim=victim,
        suspects=[_character(bundle, s) for s in t0.suspect_ids],
        locations=[LocationView(location_id=loc.location_id, name=loc.name, restricted=loc.is_restricted,
                                x=loc.x, y=loc.y) for loc in setting.locations],
        crime_location_id=t0.crime_location_id,
        crime_window_start=w.start_min,
        crime_window_end=w.end_min,
    )


def player_brief(session: Session) -> PlayerBrief:
    """Your own T2: you play this character, so you may know what it knows (PRD 5.2)."""
    pack = session.bundle.t2_knowledge[session.player_id]
    timeline = sorted(
        {(f.time_interval.start_min, f.location_id) for f in pack.private_facts
         if f.subject_id == session.player_id and f.location_id and f.time_interval}
    )
    statement = next((c.free_text for c in pack.cover_story), None)
    return PlayerBrief(
        character=_character(session.bundle, session.player_id),
        role=session.role,
        you_are_the_culprit=session.role == "culprit",
        where_you_really_were=[TimelineEntry(minute=m, location_id=loc) for m, loc in timeline],
        your_secrets=[s.description for s in (pack.character.secrets if pack.character else [])],
        your_statement_so_far=statement,
    )


def _question(session: Session) -> QuestionView | None:
    q = session.pending
    if q is None:
        return None
    return QuestionView(kind=q.kind, suspect_id=q.suspect_id, minute=q.minute, text=q.label(),
                        for_you=q.suspect_id == session.player_id)


def session_view(session: Session) -> SessionView:
    t1, setting = session.t1, session.bundle.setting
    flags = StructuredConsistencyEngine.evaluate_session(t1, setting)
    disagreements = StructuredConsistencyEngine.find_disagreements(t1, setting)
    return SessionView(
        session_id=session.session_id,
        case_id=session.bundle.t0_public.case_id,
        your_character_id=session.player_id,
        turn=session.turn,
        budget=8,
        status=session.status,
        pending_question=_question(session),
        facts=[FactView(fact_id=f.fact_id, description=f.description, subject_id=f.subject_id,
                        location_id=f.location_id, minute=f.time_interval.start_min if f.time_interval else None,
                        category=f.category.value, provenance=f.provenance.value, reliability=f.reliability,
                        status=f.status.value) for f in t1.discovered_facts],
        claims=[ClaimView(claim_id=c.claim_id, speaker_id=c.speaker_id, location_id=c.claimed_location_id,
                          minute_start=c.claimed_time_interval.start_min if c.claimed_time_interval else None,
                          minute_end=c.claimed_time_interval.end_min if c.claimed_time_interval else None,
                          observed_character_ids=c.observed_character_ids, free_text=c.free_text,
                          provenance=c.provenance.value, status=c.status.value, turn=c.turn_index)
                for c in t1.recorded_claims],
        contradictions=[_flag(f) for f in flags],
        disagreements=[DisagreementView(disagreement_id=d.disagreement_id, suspect_ids=list(d.suspect_ids),
                                        claim_ids=list(d.claim_ids), explanation=d.explanation) for d in disagreements],
        ranking=session.ranking,
        previous_ranking=session.previous_probabilities,
        detective_log=[DetectiveAction(**e) for e in session.detective_log],
        prediction_log=[PredictionLogEntry(**e) for e in session.prediction_log],
    )


def _flag(f) -> ContradictionView:
    return ContradictionView(flag_id=f.flag_id, type=f.contradiction_type.value, suspect_id=f.suspect_id,
                             claim_id=f.primary_claim_id, source_ids=f.linked_source_ids or [f.conflicting_source_id],
                             explanation=f.explanation)


def verdict_view(session: Session) -> VerdictView:
    ranking = session.verdict["ranking"]
    leader = ranking.leading_suspect_id
    facts = {f.fact_id: f.description for f in session.t1.discovered_facts}
    claims = {c.claim_id: c.free_text or c.claim_id for c in session.t1.recorded_claims}
    supporting: list[EvidenceItem] = []
    if leader:
        expl = next(e for e in ranking.explanations if e.suspect_id == leader)
        seen = set()
        for feature, ids in sorted(expl.evidence.items(), key=lambda kv: -expl.contributions.get(kv[0], 0.0)):
            if expl.contributions.get(feature, 0.0) <= 0:
                continue
            for i in ids:
                if i not in seen:
                    seen.add(i)
                    supporting.append(EvidenceItem(evidence_id=i, text=facts.get(i) or claims.get(i, i)))
    flags = StructuredConsistencyEngine.evaluate_session(session.t1, session.bundle.setting)
    return VerdictView(
        abstained=ranking.abstain,
        abstain_reason=ranking.abstain_reason,
        leading_suspect_id=leader,
        leading_probability=ranking.probabilities.get(leader) if leader else None,
        supporting_evidence=supporting[:8],
        contradictions=[_flag(f) for f in flags if f.suspect_id == leader] if leader else [],
        alternatives={s: p for s, p in sorted(ranking.probabilities.items(), key=lambda kv: -kv[1]) if s != leader},
        model_version=ranking.model_version,
    )


def _solution_sentence(session: Session) -> str:
    t3, bundle = session.bundle.t3_canonical, session.bundle
    murder = next(e for e in t3.canonical_events if e.event_kind == "MURDER")
    rooms = {loc.location_id: loc.name for loc in bundle.setting.locations}
    killer = _character(bundle, t3.culprit_id).name
    victim = _character(bundle, bundle.t0_public.victim_id).name
    m = murder.tick_min
    return f"{killer} killed {victim} in the {rooms[t3.crime_location_id]} at {m // 60:02d}:{m % 60:02d}."


def results_view(session: Session) -> ResultsView:
    """Only callable after a verdict; the one view that reads T3, with canaries stripped."""
    t3 = session.bundle.t3_canonical
    verdict = verdict_view(session)
    return ResultsView(
        culprit_id=t3.culprit_id,
        culprit_name=_character(session.bundle, t3.culprit_id).name,
        solution=_solution_sentence(session),
        machine_verdict=verdict,
        machine_was_right=None if verdict.abstained else verdict.leading_suspect_id == t3.culprit_id,
        your_role=session.role,
        lies=[LieView(suspect_id=a.liar_id, kind=a.kind.value, note=strip_canaries(a.note)) for a in t3.lie_annotations],
    )
