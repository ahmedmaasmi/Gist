# backend/app/engine/consistency.py

from app.domain.enums import ContradictionType, VerificationStatus
from app.domain.setting import SettingTemplate
from app.domain.tiers import T1Session
from app.domain.world import Claim, ContradictionFlag, Disagreement, Fact, TimeInterval


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
    def ruled_out_minutes(
        location_id: str,
        interval: TimeInterval,
        sightings: list[tuple[str, TimeInterval]],
        setting: SettingTemplate,
    ) -> set[int]:
        """
        Minutes of `interval` at which someone cannot be at `location_id`, given `sightings`
        (location, time) of that person elsewhere. Being at another location during [s, e] rules
        out [s - travel + 1, e + travel - 1] (the same rule as the timeline solver).
        """
        ruled_out: set[int] = set()
        for other_loc, when in sightings:
            if other_loc == location_id:
                continue
            reach = max(setting.get_travel_time(other_loc, location_id) - 1, 0)
            lo = max(interval.start_min, when.start_min - reach)
            hi = min(interval.end_min, when.end_min + reach)
            ruled_out.update(range(lo, hi + 1))
        return ruled_out

    @classmethod
    def _facts_ruling_out_presence(
        cls,
        subject_id: str,
        location_id: str,
        interval: TimeInterval,
        facts: list[Fact],
        setting: SettingTemplate,
    ) -> list[Fact]:
        """
        Returns the records that together make it impossible for `subject_id` to be at `location_id`
        at ANY minute of `interval` (empty list if some minute remains possible).
        """
        relevant = [
            f
            for f in facts
            if f.subject_id == subject_id
            and f.location_id != location_id
            and cls.ruled_out_minutes(location_id, interval, [(f.location_id, f.time_interval)], setting)
        ]
        sightings = [(f.location_id, f.time_interval) for f in relevant]
        all_minutes = interval.end_min - interval.start_min + 1
        if relevant and len(cls.ruled_out_minutes(location_id, interval, sightings, setting)) == all_minutes:
            return relevant
        return []

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
    def find_disagreements(
        cls,
        session: T1Session,
        setting: SettingTemplate,
    ) -> list[Disagreement]:
        """
        Cross-speaker check (D-016): B claims to have seen A at X during [b1, b2]; A claims to have
        been at L throughout [a1, a2]. If A's own claim, treated like a sighting, rules out every
        minute of [b1, b2] at X, the two claims cannot both be true. Neither speaker is blamed.
        """
        claims = sorted(session.recorded_claims, key=lambda c: (c.turn_index, c.claim_id))
        own_whereabouts = [
            c
            for c in claims
            if c.subject_id == c.speaker_id
            and c.claimed_location_id is not None
            and c.claimed_time_interval is not None
        ]
        found: list[Disagreement] = []
        seen: set[tuple[str, str]] = set()
        for b_claim in claims:
            if b_claim.claimed_location_id is None or b_claim.claimed_time_interval is None:
                continue
            for observed_id in b_claim.observed_character_ids:
                if observed_id == b_claim.speaker_id:
                    continue
                for a_claim in own_whereabouts:
                    if a_claim.speaker_id != observed_id:
                        continue
                    key = tuple(sorted((a_claim.claim_id, b_claim.claim_id)))
                    if key in seen:
                        continue
                    window = b_claim.claimed_time_interval
                    ruled_out = cls.ruled_out_minutes(
                        b_claim.claimed_location_id,
                        window,
                        [(a_claim.claimed_location_id, a_claim.claimed_time_interval)],
                        setting,
                    )
                    if len(ruled_out) < window.end_min - window.start_min + 1:
                        continue
                    seen.add(key)
                    found.append(
                        Disagreement(
                            disagreement_id=f"dis_{key[0]}_{key[1]}",
                            case_id=session.case_id,
                            suspect_ids=(b_claim.speaker_id, a_claim.speaker_id),
                            claim_ids=(b_claim.claim_id, a_claim.claim_id),
                            explanation=(
                                f"'{b_claim.speaker_id}' says they saw '{observed_id}' at "
                                f"'{b_claim.claimed_location_id}' during [{window.start_min}, {window.end_min}], "
                                f"but '{observed_id}' says they were at '{a_claim.claimed_location_id}' "
                                f"throughout [{a_claim.claimed_time_interval.start_min}, "
                                f"{a_claim.claimed_time_interval.end_min}]. At least one of them is wrong."
                            ),
                        )
                    )
        return found

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

