# backend/app/engine/solver.py
from typing import Optional
from pydantic import BaseModel, Field

from app.domain.enums import (
    ContradictionType,
    EvidenceCategory,
    ProvenanceClass,
    VerificationStatus,
)
from app.domain.setting import SettingTemplate
from app.domain.simulation import SimulatedCaseBundle
from app.domain.tiers import T0Public, T1Session
from app.domain.world import ContradictionFlag, Fact, TimeInterval
from app.engine.consistency import StructuredConsistencyEngine


class SymbolicTimelineSolver:
    """
    PRD Section 8.5 Baseline:
    Purely symbolic timeline solver operating strictly on T0Public, T1Session,
    and SettingTemplate (zero T3 access).

    Eliminates suspects whose high-reliability established RECORD/PHYSICAL facts
    make it physically impossible to reach the crime location at any point during
    the murder window, and outputs a probability distribution over suspects.
    """

    HIGH_RELIABILITY_THRESHOLD: float = 0.85
    ELIGIBLE_PROVENANCES: tuple[ProvenanceClass, ...] = (
        ProvenanceClass.RECORD,
        ProvenanceClass.PHYSICAL,
    )

    @classmethod
    def find_eliminated_suspects(
        cls,
        t0: T0Public,
        t1: T1Session,
        setting: SettingTemplate,
        crime_location_id: Optional[str] = None,
        murder_window: Optional[TimeInterval] = None,
    ) -> dict[str, str]:
        """
        Inspects high-reliability established facts (status == ESTABLISHED,
        provenance in (RECORD, PHYSICAL), reliability >= 0.85) and determines
        which suspects cannot be at `crime_location_id` at any minute during
        `murder_window`.

        Specifically, if an established record proves a suspect was at `loc_X`
        (`loc_X != crime_location_id`) during `[t_start, t_end]`, then the suspect
        cannot be at `crime_location_id` during
        `[t_start - travel_time + 1, t_end + travel_time - 1]`.
        If the entire `murder_window` is covered by one or more such blocked
        intervals, the suspect is eliminated.
        """
        target_crime_loc = crime_location_id or t0.crime_location_id
        target_window = murder_window or t0.crime_window
        if target_window is None:
            return {}

        eliminated: dict[str, str] = {}

        # Filter to high-reliability established RECORD / PHYSICAL facts with spatial-temporal slots
        reliable_facts: list[Fact] = [
            f
            for f in t1.discovered_facts
            if f.status == VerificationStatus.ESTABLISHED
            and f.provenance in cls.ELIGIBLE_PROVENANCES
            and f.reliability >= cls.HIGH_RELIABILITY_THRESHOLD
            and f.subject_id is not None
            and f.location_id is not None
            and f.time_interval is not None
        ]

        window_start = target_window.start_min
        window_end = target_window.end_min
        murder_minutes = list(range(window_start, window_end + 1))

        for suspect_id in t0.suspect_ids:
            suspect_facts = [
                f
                for f in reliable_facts
                if f.subject_id == suspect_id and f.location_id != target_crime_loc
            ]
            if not suspect_facts:
                continue

            blocked_intervals: list[tuple[int, int, Fact, int]] = []
            for fact in suspect_facts:
                assert fact.location_id is not None
                assert fact.time_interval is not None
                travel_time = setting.get_travel_time(fact.location_id, target_crime_loc)
                t_start = fact.time_interval.start_min
                t_end = fact.time_interval.end_min

                if travel_time > 0:
                    b_start = t_start - travel_time + 1
                    b_end = t_end + travel_time - 1
                else:
                    b_start = t_start
                    b_end = t_end

                if b_end >= window_start and b_start <= window_end:
                    blocked_intervals.append((b_start, b_end, fact, travel_time))

            if not blocked_intervals:
                continue

            # Check whether every minute of murder_window is blocked
            all_minutes_blocked = all(
                any(b_start <= m <= b_end for b_start, b_end, _, _ in blocked_intervals)
                for m in murder_minutes
            )

            if all_minutes_blocked:
                blocking_descriptions = [
                    (
                        f"fact '{fact.fact_id}' ({fact.provenance.value}, "
                        f"reliability={fact.reliability:.2f}) places '{suspect_id}' at "
                        f"'{fact.location_id}' during [{fact.time_interval.start_min}, "
                        f"{fact.time_interval.end_min}] (travel time to "
                        f"'{target_crime_loc}'={travel_time} min, blocking "
                        f"[{b_start}, {b_end}])"
                    )
                    for b_start, b_end, fact, travel_time in blocked_intervals
                    if fact.time_interval is not None
                ]
                eliminated[suspect_id] = (
                    f"Suspect '{suspect_id}' eliminated: impossible to reach crime scene "
                    f"'{target_crime_loc}' during murder window "
                    f"[{window_start}, {window_end}] because "
                    + "; ".join(blocking_descriptions)
                    + "."
                )

        return eliminated

    @classmethod
    def predict_distribution(
        cls,
        t0: T0Public,
        t1: T1Session,
        setting: SettingTemplate,
        crime_location_id: Optional[str] = None,
        murder_window: Optional[TimeInterval] = None,
        eps: float = 0.0,
        tie_break_by_evidence: bool = False,
    ) -> dict[str, float]:
        """
        Produces a probability distribution over `t0.suspect_ids`.
        - Eliminated suspects receive `0.0` (or `eps` before renormalization if `eps > 0`).
        - Remaining plausible suspects receive uniform `1.0 / num_remaining` (or lightly
          weighted by non-eliminated motive/access counts if `tie_break_by_evidence=True`).
        - If all suspects are eliminated, falls back to uniform `1.0 / len(t0.suspect_ids)`.
        """
        suspect_ids = list(t0.suspect_ids)
        num_total = len(suspect_ids)
        if num_total == 0:
            return {}

        eliminated = cls.find_eliminated_suspects(
            t0=t0,
            t1=t1,
            setting=setting,
            crime_location_id=crime_location_id,
            murder_window=murder_window,
        )
        remaining = [s for s in suspect_ids if s not in eliminated]

        # Fallback if all suspects were somehow eliminated
        if not remaining:
            uniform_p = 1.0 / num_total
            return {s: uniform_p for s in suspect_ids}

        raw_weights: dict[str, float] = {}
        for s in suspect_ids:
            if s in eliminated:
                raw_weights[s] = max(0.0, eps)
            else:
                if tie_break_by_evidence:
                    ev_count = sum(
                        1
                        for f in t1.discovered_facts
                        if f.subject_id == s
                        and f.category in (EvidenceCategory.MOTIVE, EvidenceCategory.ACCESS)
                    )
                    raw_weights[s] = 1.0 + 0.1 * ev_count
                else:
                    raw_weights[s] = 1.0

        total_weight = sum(raw_weights.values())
        if total_weight <= 0.0:
            uniform_p = 1.0 / num_total
            return {s: uniform_p for s in suspect_ids}

        return {s: raw_weights[s] / total_weight for s in suspect_ids}


class CaseValidationReport(BaseModel):
    """
    PRD Section 7B.2, 8.2, CH-05, CL-02:
    Structured solvability and anti-triviality report returned by CaseSolvabilityValidator.
    """
    case_id: str = Field(..., min_length=1)
    is_valid: bool
    is_under_determined_hard_case: bool = Field(
        default=False,
        description=(
            "PRD 8.2: True when case is logically consistent and has red herrings, "
            "but multiple suspects remain tied/ahead of culprit on discoverable evidence."
        ),
    )
    difficulty_estimate: str = Field(
        ...,
        description="One of 'EASY', 'MEDIUM', 'HARD', or 'INVALID'",
    )
    plausible_suspect_ids: list[str] = Field(default_factory=list)
    red_herring_suspect_ids: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class CaseSolvabilityValidator:
    """
    PRD Section 7B.2, 8.2, CH-05, CL-02:
    Validates a SimulatedCaseBundle (or Case Lab authored case) for:
      1. Culprit logical possibility (culprit not eliminated by established records)
      2. Non-triviality (at least 2 plausible suspects survive timeline elimination)
      3. Red herring existence (at least 1 innocent suspect has discoverable motive, access, or contradiction)
      4. Culprit identifiability on discoverable T1 evidence (or explicit hard/under-determined mode)
    """

    @staticmethod
    def _collect_all_contradictions(
        t1: T1Session,
        setting: SettingTemplate,
    ) -> list[ContradictionFlag]:
        """
        Combines pre-populated T1 contradiction flags with flags evaluated dynamically
        by StructuredConsistencyEngine.evaluate_session, deduplicated by flag_id or key.
        """
        evaluated_flags = StructuredConsistencyEngine.evaluate_session(t1, setting)
        combined: list[ContradictionFlag] = []
        seen_keys: set[tuple[str, str, str, str]] = set()

        for flag in (*t1.contradiction_flags, *evaluated_flags):
            key = (
                flag.contradiction_type.value,
                flag.suspect_id,
                flag.primary_claim_id,
                flag.conflicting_source_id,
            )
            if key not in seen_keys:
                seen_keys.add(key)
                combined.append(flag)

        return combined

    @staticmethod
    def _compute_discoverable_support_scores(
        suspect_ids: list[str],
        t1: T1Session,
        contradictions: list[ContradictionFlag],
        crime_location_id: str,
        murder_window: TimeInterval,
    ) -> dict[str, float]:
        """
        Computes a deterministic discoverable T1 evidence support score for each suspect,
        combining reliability-weighted motive facts, access facts, crime-scene opportunity
        (timeline/forensic traces at crime_location_id overlapping murder_window),
        and CLAIM_FACT / CLAIM_CLAIM contradictions.
        """
        scores: dict[str, float] = {s: 0.0 for s in suspect_ids}
        valid_statuses = {VerificationStatus.ESTABLISHED, VerificationStatus.VERIFIED}

        for fact in t1.discovered_facts:
            if fact.status not in valid_statuses:
                continue
            subj = fact.subject_id
            if subj is None or subj not in scores:
                continue

            if fact.category == EvidenceCategory.MOTIVE:
                scores[subj] += fact.reliability
            elif fact.category == EvidenceCategory.ACCESS:
                if (
                    fact.location_id == crime_location_id
                    and fact.time_interval is not None
                    and fact.time_interval.overlaps(murder_window)
                ):
                    scores[subj] += 1.2 * fact.reliability
                else:
                    scores[subj] += 0.8 * fact.reliability
            elif fact.category in (EvidenceCategory.TIMELINE, EvidenceCategory.FORENSIC):
                if (
                    fact.location_id == crime_location_id
                    and fact.time_interval is not None
                    and fact.time_interval.overlaps(murder_window)
                ):
                    scores[subj] += 1.2 * fact.reliability

        for flag in contradictions:
            if flag.suspect_id not in scores:
                continue
            if flag.contradiction_type == ContradictionType.CLAIM_FACT:
                scores[flag.suspect_id] += 1.0
            elif flag.contradiction_type == ContradictionType.CLAIM_CLAIM:
                scores[flag.suspect_id] += 0.5

        return scores

    @classmethod
    def validate_case(
        cls,
        bundle: SimulatedCaseBundle,
        setting: SettingTemplate,
        allow_hard_cases: bool = False,
    ) -> CaseValidationReport:
        """
        Runs the 4-stage solvability and anti-triviality validation checks on `bundle`.
        """
        t0 = bundle.t0_public
        t1 = bundle.t1_session
        t3 = bundle.t3_canonical
        culprit_id = t3.culprit_id
        crime_location_id = t0.crime_location_id or t3.crime_location_id
        murder_window = t0.crime_window or t3.crime_window

        eliminated_suspects = SymbolicTimelineSolver.find_eliminated_suspects(
            t0=t0,
            t1=t1,
            setting=setting,
            crime_location_id=crime_location_id,
            murder_window=murder_window,
        )
        contradictions = cls._collect_all_contradictions(t1=t1, setting=setting)

        plausible_suspect_ids = [
            s for s in t0.suspect_ids if s not in eliminated_suspects
        ]

        failure_reasons: list[str] = []
        suggestions: list[str] = []

        # ------------------------------------------------------------------
        # Check 1: Culprit Logical Possibility (PRD 8.2)
        # ------------------------------------------------------------------
        if culprit_id in eliminated_suspects:
            failure_reasons.append(
                "Canonical culprit was logically eliminated by established T1 timeline records"
            )
            suggestions.append(
                "Adjust culprit schedule or reduce record reliability"
            )

        # ------------------------------------------------------------------
        # Check 2: No Single-Clue Triviality (PRD 7B.2)
        # ------------------------------------------------------------------
        if len(plausible_suspect_ids) < 2:
            failure_reasons.append(
                "Case is trivially solved by timeline elimination alone"
            )
            suggestions.append(
                "Weaken an innocent suspect's alibi or increase record_drop_rate"
            )

        # ------------------------------------------------------------------
        # Check 3: Red Herring Existence (PRD 7B.2 & 8.2)
        # ------------------------------------------------------------------
        innocent_suspects = [s for s in t0.suspect_ids if s != culprit_id]
        red_herring_suspect_ids: list[str] = []
        for inn_id in innocent_suspects:
            has_motive_or_access = any(
                f.subject_id == inn_id
                and f.category in (EvidenceCategory.MOTIVE, EvidenceCategory.ACCESS)
                for f in t1.discovered_facts
            )
            has_contradiction = any(
                flag.suspect_id == inn_id for flag in contradictions
            )
            if has_motive_or_access or has_contradiction:
                red_herring_suspect_ids.append(inn_id)

        if len(red_herring_suspect_ids) == 0:
            failure_reasons.append(
                "No red herring exists among innocent suspects"
            )
            suggestions.append(
                "Add a secret/goal to an innocent character or lower affinity to trigger an ARGUE event"
            )

        # ------------------------------------------------------------------
        # Check 4: Culprit Identifiability from Discoverable Evidence (PRD 7B.2)
        # ------------------------------------------------------------------
        support_scores = cls._compute_discoverable_support_scores(
            suspect_ids=t0.suspect_ids,
            t1=t1,
            contradictions=contradictions,
            crime_location_id=crime_location_id,
            murder_window=murder_window,
        )

        culprit_score = support_scores.get(culprit_id, 0.0)
        innocent_plausible_scores = [
            support_scores.get(s, 0.0)
            for s in plausible_suspect_ids
            if s != culprit_id
        ]
        max_innocent_score = (
            max(innocent_plausible_scores) if innocent_plausible_scores else 0.0
        )
        score_margin = culprit_score - max_innocent_score

        checks_1_to_3_passed = len(failure_reasons) == 0
        is_under_determined_hard_case = False

        if culprit_id not in plausible_suspect_ids or score_margin <= 1e-6:
            # Culprit is tied or behind an innocent plausible suspect on discoverable T1 evidence
            if checks_1_to_3_passed:
                is_under_determined_hard_case = True
            if not (allow_hard_cases and checks_1_to_3_passed):
                failure_reasons.append(
                    "Culprit does not have strictly highest discoverable T1 evidence support "
                    "(case is under-determined)"
                )
                suggestions.append(
                    "Add a witness or physical trace linking the culprit to the crime window, or re-roll the seed"
                )

        is_valid = len(failure_reasons) == 0

        # ------------------------------------------------------------------
        # Compute Difficulty Estimate
        # ------------------------------------------------------------------
        if not is_valid:
            difficulty_estimate = "INVALID"
        elif is_under_determined_hard_case or score_margin < 0.6:
            difficulty_estimate = "HARD"
        elif len(plausible_suspect_ids) == 2 and score_margin >= 1.5:
            difficulty_estimate = "EASY"
        else:
            difficulty_estimate = "MEDIUM"

        return CaseValidationReport(
            case_id=t0.case_id,
            is_valid=is_valid,
            is_under_determined_hard_case=is_under_determined_hard_case,
            difficulty_estimate=difficulty_estimate,
            plausible_suspect_ids=plausible_suspect_ids,
            red_herring_suspect_ids=red_herring_suspect_ids,
            failure_reasons=failure_reasons,
            suggestions=suggestions,
        )

