# backend/app/engine/consistency.py

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
    ) -> str | None:
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
                            linked_source_ids=[fact.fact_id],
                            explanation=(
                                f"Claim '{claim.claim_id}' about '{claim.subject_id}' conflicts "
                                f"with fact '{fact.fact_id}': {reason}"
                            ),
                            is_semantic=False,
                        )
                    )

        # Check 2: Observed Characters vs Facts.
        # "I saw Y at L during [a, b]" means Y was at L at *some* moment in [a, b], not throughout.
        # It is contradicted only if Y's records make every minute of [a, b] impossible.
        located = [
            f
            for f in facts
            if f.status in valid_statuses and f.location_id is not None and f.time_interval is not None
        ]
        for observed_id in claim.observed_character_ids:
            if observed_id == claim.subject_id:
                continue
            blocking = cls._facts_ruling_out_presence(
                observed_id,
                claim.claimed_location_id,
                claim.claimed_time_interval,
                located,
                setting,
            )
            if blocking:
                record_list = ", ".join(
                    f"'{f.fact_id}' ({f.location_id} at {f.time_interval.start_min})" for f in blocking
                )
                flags.append(
                    ContradictionFlag(
                        flag_id=f"flag_{claim.claim_id}_obs_{observed_id}",
                        case_id=claim.case_id,
                        suspect_id=claim.speaker_id,
                        contradiction_type=ContradictionType.CLAIM_FACT,
                        primary_claim_id=claim.claim_id,
                        conflicting_source_id=blocking[0].fact_id,
                        linked_source_ids=[f.fact_id for f in blocking],
                        explanation=(
                            f"Speaker '{claim.speaker_id}' claimed to observe '{observed_id}' at "
                            f"'{claim.claimed_location_id}' during [{claim.claimed_time_interval.start_min}, "
                            f"{claim.claimed_time_interval.end_min}], but records {record_list} place "
                            f"'{observed_id}' too far away at every minute of that interval."
                        ),
                        is_semantic=False,
                    )
                )

        return flags

    @staticmethod
    def _facts_ruling_out_presence(
        subject_id: str,
        location_id: str,
        interval: TimeInterval,
        facts: list[Fact],
        setting: SettingTemplate,
    ) -> list[Fact]:
        """
        Returns the records that together make it impossible for `subject_id` to be at `location_id`
        at ANY minute of `interval` (empty list if some minute remains possible). A record at another
        location at minute t rules out [t - travel + 1, t + travel - 1], as in the timeline solver.
        """
        blocks: list[tuple[int, int, Fact]] = []
        for fact in facts:
            if fact.subject_id != subject_id or fact.location_id == location_id:
                continue
            travel = setting.get_travel_time(fact.location_id, location_id)
            reach = max(travel - 1, 0)
            b_start = fact.time_interval.start_min - reach
            b_end = fact.time_interval.end_min + reach
            if b_end >= interval.start_min and b_start <= interval.end_min:
                blocks.append((b_start, b_end, fact))
        if not blocks:
            return []
        every_minute_blocked = all(
            any(b_start <= m <= b_end for b_start, b_end, _ in blocks)
            for m in range(interval.start_min, interval.end_min + 1)
        )
        return [fact for _, _, fact in blocks] if every_minute_blocked else []

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
                        linked_source_ids=[prior.claim_id],
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

