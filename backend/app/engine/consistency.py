# backend/app/engine/consistency.py
from typing import Optional

from app.domain.enums import ContradictionType, VerificationStatus
from app.domain.setting import SettingTemplate
from app.domain.tiers import T1Session
from app.domain.world import Claim, ContradictionFlag, Fact, TimeInterval


class StructuredConsistencyEngine:
    """
    PRD Section 6.4.B, Section 7B.2, and Requirement MD-05:
    Layer 1 Deterministic Consistency Engine.

    Strictly inspects T1Session data (established/verified facts and recorded claims)
    and SettingTemplate spatial geometry—never T2 or T3.
    """

    @staticmethod
    def _check_spatiotemporal_conflict(
        loc_a: str,
        interval_a: TimeInterval,
        loc_b: str,
        interval_b: TimeInterval,
        setting: SettingTemplate,
    ) -> Optional[str]:
        """
        Checks whether being at `loc_a` during `interval_a` and `loc_b` during `interval_b`
        violates direct time overlap (Rule A) or minimum travel time feasibility (Rule B).
        """
        if loc_a == loc_b:
            return None

        # Rule A: Direct Time Overlap in Different Locations
        if interval_a.overlaps(interval_b):
            return (
                f"Spatiotemporal overlap conflict: cannot be at '{loc_a}' during "
                f"[{interval_a.start_min}, {interval_a.end_min}] and at '{loc_b}' during "
                f"[{interval_b.start_min}, {interval_b.end_min}]."
            )

        # Rule B: Travel Time Feasibility (non-overlapping intervals in different locations)
        if interval_a.end_min < interval_b.start_min:
            gap = interval_b.start_min - interval_a.end_min
            required_travel = setting.get_travel_time(loc_a, loc_b)
            origin, dest = loc_a, loc_b
        elif interval_b.end_min < interval_a.start_min:
            gap = interval_a.start_min - interval_b.end_min
            required_travel = setting.get_travel_time(loc_b, loc_a)
            origin, dest = loc_b, loc_a
        else:
            return None

        if gap < required_travel:
            return (
                f"Travel time conflict: moving between '{origin}' and '{dest}' takes "
                f"{required_travel} minutes, but only {gap} minutes elapsed "
                f"([{interval_a.start_min}, {interval_a.end_min}] vs "
                f"[{interval_b.start_min}, {interval_b.end_min}])."
            )

        return None

    @classmethod
    def check_claim_against_facts(
        cls,
        claim: Claim,
        facts: list[Fact],
        setting: SettingTemplate,
    ) -> list[ContradictionFlag]:
        """
        Compares a single claim against ESTABLISHED or VERIFIED facts with structured
        location and time_interval slots.
        """
        flags: list[ContradictionFlag] = []

        if claim.claimed_location_id is None or claim.claimed_time_interval is None:
            return flags

        valid_statuses = (VerificationStatus.ESTABLISHED, VerificationStatus.VERIFIED)

        for fact in facts:
            if fact.status not in valid_statuses:
                continue
            if fact.location_id is None or fact.time_interval is None:
                continue

            # Check 1: Subject Whereabouts vs Fact
            if fact.subject_id == claim.subject_id:
                reason = cls._check_spatiotemporal_conflict(
                    claim.claimed_location_id,
                    claim.claimed_time_interval,
                    fact.location_id,
                    fact.time_interval,
                    setting,
                )
                if reason is not None:
                    flags.append(
                        ContradictionFlag(
                            flag_id=f"flag_{claim.claim_id}_{fact.fact_id}_subject",
                            case_id=claim.case_id,
                            suspect_id=claim.speaker_id,
                            contradiction_type=ContradictionType.CLAIM_FACT,
                            primary_claim_id=claim.claim_id,
                            conflicting_source_id=fact.fact_id,
                            explanation=(
                                f"Claim '{claim.claim_id}' about '{claim.subject_id}' conflicts "
                                f"with fact '{fact.fact_id}': {reason}"
                            ),
                            is_semantic=False,
                        )
                    )

            # Check 2: Observed Character vs Fact
            for observed_id in claim.observed_character_ids:
                if observed_id == claim.subject_id:
                    continue
                if fact.subject_id == observed_id:
                    reason = cls._check_spatiotemporal_conflict(
                        claim.claimed_location_id,
                        claim.claimed_time_interval,
                        fact.location_id,
                        fact.time_interval,
                        setting,
                    )
                    if reason is not None:
                        flags.append(
                            ContradictionFlag(
                                flag_id=f"flag_{claim.claim_id}_{fact.fact_id}_obs_{observed_id}",
                                case_id=claim.case_id,
                                suspect_id=claim.speaker_id,
                                contradiction_type=ContradictionType.CLAIM_FACT,
                                primary_claim_id=claim.claim_id,
                                conflicting_source_id=fact.fact_id,
                                explanation=(
                                    f"Speaker '{claim.speaker_id}' claimed to observe "
                                    f"'{observed_id}' at '{claim.claimed_location_id}', "
                                    f"conflicting with fact '{fact.fact_id}': {reason}"
                                ),
                                is_semantic=False,
                            )
                        )

        return flags

    @classmethod
    def check_claim_against_claims(
        cls,
        new_claim: Claim,
        prior_claims: list[Claim],
        setting: SettingTemplate,
    ) -> list[ContradictionFlag]:
        """
        Compares `new_claim` against earlier claims made by the same speaker about the same subject.
        """
        flags: list[ContradictionFlag] = []

        if new_claim.claimed_location_id is None or new_claim.claimed_time_interval is None:
            return flags

        for prior in prior_claims:
            if prior.speaker_id != new_claim.speaker_id or prior.claim_id == new_claim.claim_id:
                continue
            if prior.claimed_location_id is None or prior.claimed_time_interval is None:
                continue
            if prior.subject_id != new_claim.subject_id:
                continue

            reason = cls._check_spatiotemporal_conflict(
                new_claim.claimed_location_id,
                new_claim.claimed_time_interval,
                prior.claimed_location_id,
                prior.claimed_time_interval,
                setting,
            )
            if reason is not None:
                flags.append(
                    ContradictionFlag(
                        flag_id=f"flag_{new_claim.claim_id}_{prior.claim_id}",
                        case_id=new_claim.case_id,
                        suspect_id=new_claim.speaker_id,
                        contradiction_type=ContradictionType.CLAIM_CLAIM,
                        primary_claim_id=new_claim.claim_id,
                        conflicting_source_id=prior.claim_id,
                        explanation=(
                            f"Speaker '{new_claim.speaker_id}' contradicted earlier claim "
                            f"'{prior.claim_id}' with new claim '{new_claim.claim_id}': {reason}"
                        ),
                        is_semantic=False,
                    )
                )

        return flags

    @classmethod
    def evaluate_session(
        cls,
        session: T1Session,
        setting: SettingTemplate,
    ) -> list[ContradictionFlag]:
        """
        Iterates through `session.recorded_claims` in chronological `turn_index` order,
        running both `check_claim_against_facts` and `check_claim_against_claims`
        (against strictly earlier claims so pairs aren't double-counted), and returns
        the deduplicated list of all `ContradictionFlag` objects.
        """
        ordered_claims = sorted(session.recorded_claims, key=lambda c: c.turn_index)
        all_flags: list[ContradictionFlag] = []
        seen_keys: set[tuple[ContradictionType, str, str, str]] = set()

        for idx, claim in enumerate(ordered_claims):
            prior_claims = ordered_claims[:idx]

            claim_fact_flags = cls.check_claim_against_facts(
                claim=claim,
                facts=session.discovered_facts,
                setting=setting,
            )
            claim_claim_flags = cls.check_claim_against_claims(
                new_claim=claim,
                prior_claims=prior_claims,
                setting=setting,
            )

            for flag in (*claim_fact_flags, *claim_claim_flags):
                dedup_key = (
                    flag.contradiction_type,
                    flag.suspect_id,
                    flag.primary_claim_id,
                    flag.conflicting_source_id,
                )
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    all_flags.append(flag)

        return all_flags

