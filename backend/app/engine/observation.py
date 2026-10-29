# backend/app/engine/observation.py
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.domain.character import Character, CharacterSecret, RelationshipGraph
from app.domain.enums import (
    EvidenceCategory,
    InteractionType,
    ProvenanceClass,
    VerificationStatus,
)
from app.domain.setting import SettingTemplate
from app.domain.tiers import T1Session, T2CharacterKnowledge, T3Canonical
from app.domain.world import CanonicalEvent, Claim, Fact, SimulationConfig, TimeInterval


class ObservationModel:
    """
    PRD Section 7A.4 & Section 8.2:
    Derives T1Session (player-visible facts and initial suspect claims) and
    T2CharacterKnowledge (per-character private facts, secrets, and cover stories)
    from the T3 canonical event log without leaking T3 canary tokens or ground truth.
    """

    @staticmethod
    def _planned_location_for_window(
        character: Character,
        window: TimeInterval,
        setting: SettingTemplate,
    ) -> str:
        """Returns the character's scheduled location overlapping the window, or a fallback."""
        best_loc: Optional[str] = None
        best_overlap = -1
        for slot in character.schedule:
            overlap = slot.time_interval.overlap_duration(window)
            if overlap > best_overlap:
                best_overlap = overlap
                best_loc = slot.planned_location_id
        if best_loc is not None:
            return best_loc
        if setting.locations:
            return setting.locations[0].location_id
        return "loc_default"

    @staticmethod
    def _non_crime_location(
        preferred_loc: str,
        crime_location_id: str,
        setting: SettingTemplate,
    ) -> str:
        """Ensures a false alibi location is distinct from the crime scene when possible."""
        if preferred_loc != crime_location_id:
            return preferred_loc
        for loc in setting.locations:
            if loc.location_id != crime_location_id:
                return loc.location_id
        return preferred_loc

    @classmethod
    def derive(
        cls,
        config: SimulationConfig,
        setting: SettingTemplate,
        characters: list[Character],
        relationship_graph: RelationshipGraph,
        canonical_events: list[CanonicalEvent],
        t3_canonical: T3Canonical,
        rng: Optional[random.Random] = None,
    ) -> tuple[T1Session, dict[str, T2CharacterKnowledge]]:
        """
        Derives (T1Session, dict[str, T2CharacterKnowledge]) deterministically from T3 state.
        """
        local_rng = rng if rng is not None else random.Random(config.seed + 1000)
        char_map: dict[str, Character] = {c.character_id: c for c in characters}
        restricted_locs: set[str] = {
            loc.location_id for loc in setting.locations if loc.is_restricted
        }
        culprit_id = t3_canonical.culprit_id

        # ------------------------------------------------------------------
        # 1. Derive T1 Facts
        # ------------------------------------------------------------------
        t1_facts: list[Fact] = []
        fact_counter = 0

        def next_t1_fact_id(prefix: str) -> str:
            nonlocal fact_counter
            fact_counter += 1
            return f"fact_{config.case_id}_{prefix}_{fact_counter:03d}"

        # 1a. Movement / Access facts at restricted locations or crime_location_id
        crime_trace_emitted_for_culprit = False
        for event in canonical_events:
            if event.event_kind != "MOVEMENT":
                continue

            is_crime_loc = event.location_id == config.crime_location_id
            is_restricted = event.location_id in restricted_locs
            if not (is_crime_loc or is_restricted):
                continue

            event_interval = TimeInterval(
                start_min=event.tick_min,
                end_min=event.tick_min + config.tick_size_min,
            )
            in_murder_window = config.murder_window.overlaps(event_interval)
            is_culprit_crime_move = (
                event.actor_id == culprit_id and is_crime_loc and in_murder_window
            )

            # Always preserve key crime-window trace for culprit; apply record_drop_rate to others
            if is_culprit_crime_move:
                should_emit = True
            else:
                should_emit = local_rng.random() >= config.record_drop_rate

            if should_emit:
                prov = ProvenanceClass.RECORD if is_restricted else ProvenanceClass.PHYSICAL
                cat = EvidenceCategory.ACCESS if is_restricted else EvidenceCategory.TIMELINE
                rel = round(
                    max(0.75, min(0.98, 0.92 - config.witness_noise_rate * 0.15)),
                    2,
                )
                t1_facts.append(
                    Fact(
                        fact_id=next_t1_fact_id("move"),
                        case_id=config.case_id,
                        description=(
                            f"Access/movement trace places {event.actor_id} at "
                            f"{event.location_id} around minute {event.tick_min}."
                        ),
                        subject_id=event.actor_id,
                        location_id=event.location_id,
                        time_interval=event_interval,
                        category=cat,
                        provenance=prov,
                        reliability=rel,
                        status=VerificationStatus.ESTABLISHED,
                    )
                )
                if is_culprit_crime_move:
                    crime_trace_emitted_for_culprit = True
                    # Also emit a forensic physical trace at the crime scene
                    t1_facts.append(
                        Fact(
                            fact_id=next_t1_fact_id("forensic"),
                            case_id=config.case_id,
                            description=(
                                f"Physical trace of {event.actor_id} recovered at "
                                f"{event.location_id} from window "
                                f"[{event_interval.start_min}, {event_interval.end_min}]."
                            ),
                            subject_id=event.actor_id,
                            location_id=event.location_id,
                            time_interval=event_interval,
                            category=EvidenceCategory.FORENSIC,
                            provenance=ProvenanceClass.PHYSICAL,
                            reliability=0.90,
                            status=VerificationStatus.ESTABLISHED,
                        )
                    )

        # Fallback guarantee: ensure at least one key crime-window trace exists for culprit
        if not crime_trace_emitted_for_culprit:
            t1_facts.append(
                Fact(
                    fact_id=next_t1_fact_id("crime_trace"),
                    case_id=config.case_id,
                    description=(
                        f"Crime-scene log records {culprit_id} entering "
                        f"{config.crime_location_id} during the murder window."
                    ),
                    subject_id=culprit_id,
                    location_id=config.crime_location_id,
                    time_interval=config.murder_window,
                    category=EvidenceCategory.TIMELINE,
                    provenance=ProvenanceClass.RECORD,
                    reliability=0.92,
                    status=VerificationStatus.ESTABLISHED,
                )
            )

        # 1b. Witness facts from ARGUE events with bystanders
        for event in canonical_events:
            if (
                event.event_kind == "INTERACTION"
                and event.interaction_type == InteractionType.ARGUE
                and len(event.witness_ids) > 0
            ):
                witness_id = event.witness_ids[0]
                witness_char = char_map.get(witness_id)
                if witness_char is not None:
                    trait_quality = (
                        witness_char.traits.honesty + witness_char.traits.composure
                    ) / 2.0
                else:
                    trait_quality = 0.65

                raw_rel = (
                    0.55
                    + 0.35 * trait_quality * (1.0 - config.witness_noise_rate * 0.5)
                )
                reliability = round(max(0.55, min(0.90, raw_rel)), 2)

                t1_facts.append(
                    Fact(
                        fact_id=next_t1_fact_id("argue_witness"),
                        case_id=config.case_id,
                        description=(
                            f"Witness {witness_id} overheard a heated argument between "
                            f"{event.actor_id} and {event.target_id} at {event.location_id} "
                            f"at minute {event.tick_min}."
                        ),
                        subject_id=event.actor_id,
                        target_id=event.target_id,
                        location_id=event.location_id,
                        time_interval=TimeInterval(
                            start_min=event.tick_min,
                            end_min=event.tick_min + config.tick_size_min,
                        ),
                        category=EvidenceCategory.MOTIVE,
                        provenance=ProvenanceClass.WITNESS,
                        reliability=reliability,
                        status=VerificationStatus.ESTABLISHED,
                    )
                )

        # 1c. Motive and Relationship facts from goals, secrets, and debts
        for char in sorted(characters, key=lambda c: c.character_id):
            if char.character_id == config.victim_id:
                continue
            for goal in char.goals:
                if goal.target_character_id == config.victim_id:
                    t1_facts.append(
                        Fact(
                            fact_id=next_t1_fact_id("goal_motive"),
                            case_id=config.case_id,
                            description=(
                                f"Documented motive ({goal.goal_type.value}) linking "
                                f"{char.character_id} to {config.victim_id}: {goal.description}"
                            ),
                            subject_id=char.character_id,
                            target_id=config.victim_id,
                            category=EvidenceCategory.MOTIVE,
                            provenance=ProvenanceClass.RECORD,
                            reliability=0.88,
                            status=VerificationStatus.ESTABLISHED,
                        )
                    )
            for secret in char.secrets:
                if secret.is_crime_linked:
                    t1_facts.append(
                        Fact(
                            fact_id=next_t1_fact_id("secret_motive"),
                            case_id=config.case_id,
                            description=(
                                f"Financial/personal record indicates {char.character_id} had a "
                                f"crime-linked dispute ({secret.secret_id}) involving {config.victim_id}."
                            ),
                            subject_id=char.character_id,
                            target_id=config.victim_id,
                            category=EvidenceCategory.MOTIVE,
                            provenance=ProvenanceClass.RECORD,
                            reliability=0.85,
                            status=VerificationStatus.ESTABLISHED,
                        )
                    )

        revealed_edges = []
        for edge in relationship_graph.edges:
            if (
                edge.obligation >= 0.5
                or edge.affinity <= -0.3
                or edge.is_revealed_to_player
            ):
                revealed_copy = edge.model_copy(deep=True)
                revealed_copy.is_revealed_to_player = True
                revealed_edges.append(revealed_copy)

                t1_facts.append(
                    Fact(
                        fact_id=next_t1_fact_id("rel"),
                        case_id=config.case_id,
                        description=(
                            f"Relationship record between {edge.source_id} and {edge.target_id} "
                            f"(affinity={edge.affinity:.2f}, obligation={edge.obligation:.2f})."
                        ),
                        subject_id=edge.source_id,
                        target_id=edge.target_id,
                        category=EvidenceCategory.RELATIONSHIP,
                        provenance=ProvenanceClass.RECORD,
                        reliability=0.85,
                        status=VerificationStatus.ESTABLISHED,
                    )
                )

        # ------------------------------------------------------------------
        # 2. Derive T2 Character Knowledge & Initial Alibi Claims
        # ------------------------------------------------------------------
        t2_knowledge: dict[str, T2CharacterKnowledge] = {}
        secret_lookup: dict[str, CharacterSecret] = {}
        for char in characters:
            for sec in char.secrets:
                secret_lookup[sec.secret_id] = sec

        # Track COVER_FOR pledges: covering_char_id -> covered_char_id
        cover_pledges: dict[str, str] = {}
        for event in canonical_events:
            if (
                event.event_kind == "INTERACTION"
                and event.interaction_type == InteractionType.COVER_FOR
            ):
                covering_id = str(
                    event.metadata.get("covering_character_id", event.target_id or event.actor_id)
                )
                covered_id = str(
                    event.metadata.get("covered_character_id", event.actor_id)
                )
                cover_pledges[covering_id] = covered_id

        # Track true co-located observations during murder_window
        true_murder_window_loc: dict[str, str] = {}
        true_murder_window_observed: dict[str, list[str]] = {
            c.character_id: [] for c in characters
        }
        for event in canonical_events:
            if event.event_kind == "MOVEMENT":
                ev_interval = TimeInterval(
                    start_min=event.tick_min,
                    end_min=event.tick_min + config.tick_size_min,
                )
                if config.murder_window.overlaps(ev_interval):
                    true_murder_window_loc[event.actor_id] = event.location_id
                    for wit_id in event.witness_ids:
                        if (
                            wit_id != config.victim_id
                            and wit_id not in true_murder_window_observed.get(event.actor_id, [])
                        ):
                            true_murder_window_observed.setdefault(event.actor_id, []).append(
                                wit_id
                            )

        deterministic_timestamp = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc) + timedelta(
            minutes=config.end_min
        )
        initial_claims: list[Claim] = []

        for char in sorted(characters, key=lambda c: c.character_id):
            cid = char.character_id
            private_facts: list[Fact] = []
            known_secret_ids: list[str] = [s.secret_id for s in char.secrets]
            unrelated_secrets: list[CharacterSecret] = [
                s.model_copy(deep=True) for s in char.secrets if not s.is_crime_linked
            ]

            # Own secrets as private facts
            for sec in char.secrets:
                private_facts.append(
                    Fact(
                        fact_id=f"t2_fact_{config.case_id}_{cid}_own_sec_{sec.secret_id}",
                        case_id=config.case_id,
                        description=f"Personal secret ({sec.secret_id}): {sec.description}",
                        subject_id=cid,
                        category=(
                            EvidenceCategory.MOTIVE
                            if sec.is_crime_linked
                            else EvidenceCategory.RELATIONSHIP
                        ),
                        provenance=ProvenanceClass.WITNESS,
                        reliability=1.0,
                        status=VerificationStatus.ESTABLISHED,
                    )
                )

            # Confided secrets learned via CONFIDE events
            for event in canonical_events:
                if (
                    event.event_kind == "INTERACTION"
                    and event.interaction_type == InteractionType.CONFIDE
                    and event.target_id == cid
                ):
                    sec_id = str(event.metadata.get("secret_id", ""))
                    sec_obj = secret_lookup.get(sec_id)
                    if sec_id and sec_id not in known_secret_ids:
                        known_secret_ids.append(sec_id)
                    if sec_obj is not None and not sec_obj.is_crime_linked:
                        if all(s.secret_id != sec_id for s in unrelated_secrets):
                            unrelated_secrets.append(sec_obj.model_copy(deep=True))

                    sec_desc = sec_obj.description if sec_obj is not None else sec_id
                    private_facts.append(
                        Fact(
                            fact_id=f"t2_fact_{config.case_id}_{cid}_confided_{event.event_id}",
                            case_id=config.case_id,
                            description=(
                                f"{event.actor_id} confided secret '{sec_id}' to {cid} "
                                f"at {event.location_id} (min {event.tick_min}): {sec_desc}"
                            ),
                            subject_id=event.actor_id,
                            target_id=cid,
                            location_id=event.location_id,
                            time_interval=TimeInterval(
                                start_min=event.tick_min,
                                end_min=event.tick_min + config.tick_size_min,
                            ),
                            category=(
                                EvidenceCategory.MOTIVE
                                if (sec_obj and sec_obj.is_crime_linked)
                                else EvidenceCategory.RELATIONSHIP
                            ),
                            provenance=ProvenanceClass.WITNESS,
                            reliability=0.95,
                            status=VerificationStatus.ESTABLISHED,
                        )
                    )

            # Own movements & direct observations as private facts
            for event in canonical_events:
                if event.event_kind == "MOVEMENT" and event.actor_id == cid:
                    private_facts.append(
                        Fact(
                            fact_id=f"t2_fact_{config.case_id}_{cid}_move_{event.event_id}",
                            case_id=config.case_id,
                            description=(
                                f"{cid} was at {event.location_id} at minute {event.tick_min}."
                            ),
                            subject_id=cid,
                            location_id=event.location_id,
                            time_interval=TimeInterval(
                                start_min=event.tick_min,
                                end_min=event.tick_min + config.tick_size_min,
                            ),
                            category=EvidenceCategory.TIMELINE,
                            provenance=ProvenanceClass.WITNESS,
                            reliability=1.0,
                            status=VerificationStatus.ESTABLISHED,
                        )
                    )

            cover_story: list[Claim] = []
            if cid != config.victim_id:
                planned_loc = cls._planned_location_for_window(
                    char, config.murder_window, setting
                )
                safe_alibi_loc = cls._non_crime_location(
                    planned_loc, config.crime_location_id, setting
                )
                true_loc = true_murder_window_loc.get(cid, planned_loc)

                if cid == culprit_id:
                    # Culprit alibi generation
                    if local_rng.random() < config.guilty_lie_rate:
                        claimed_loc = safe_alibi_loc
                        observed_ids: list[str] = []
                        corroborated = False
                        text = (
                            f"I remained at {claimed_loc} from {config.murder_window.start_min} "
                            f"to {config.murder_window.end_min} per my schedule."
                        )
                    else:
                        claimed_loc = config.crime_location_id
                        observed_ids = []
                        corroborated = False
                        text = (
                            f"I briefly passed through {claimed_loc} during "
                            f"[{config.murder_window.start_min}, {config.murder_window.end_min}]."
                        )
                else:
                    # Innocent suspect alibi generation
                    covered_partner = cover_pledges.get(cid)
                    has_red_herring = len(unrelated_secrets) > 0
                    lie_roll = local_rng.random()

                    if covered_partner is not None:
                        claimed_loc = safe_alibi_loc
                        observed_ids = [covered_partner]
                        corroborated = True
                        text = (
                            f"I was at {claimed_loc} with {covered_partner} throughout "
                            f"[{config.murder_window.start_min}, {config.murder_window.end_min}]."
                        )
                    elif has_red_herring and lie_roll < config.innocent_lie_rate:
                        # Evasive claim hiding red-herring secret
                        evasive_loc = cls._non_crime_location(
                            safe_alibi_loc, true_loc, setting
                        )
                        claimed_loc = evasive_loc
                        observed_ids = []
                        corroborated = False
                        text = (
                            f"I was alone at {claimed_loc} between "
                            f"{config.murder_window.start_min} and {config.murder_window.end_min}."
                        )
                    else:
                        claimed_loc = true_loc
                        observed_ids = sorted(set(true_murder_window_observed.get(cid, [])))
                        corroborated = len(observed_ids) > 0
                        text = (
                            f"I was at {claimed_loc} from {config.murder_window.start_min} "
                            f"to {config.murder_window.end_min}."
                        )

                alibi_claim = Claim(
                    claim_id=f"claim_{config.case_id}_{cid}_alibi_0",
                    case_id=config.case_id,
                    speaker_id=cid,
                    subject_id=cid,
                    turn_index=0,
                    timestamp=deterministic_timestamp,
                    claimed_location_id=claimed_loc,
                    claimed_time_interval=config.murder_window,
                    observed_character_ids=observed_ids,
                    has_corroboration_claim=corroborated,
                    free_text=text,
                    provenance=ProvenanceClass.SELF_REPORT,
                    status=VerificationStatus.UNVERIFIED,
                )
                cover_story.append(alibi_claim)
                initial_claims.append(alibi_claim)

            t2_knowledge[cid] = T2CharacterKnowledge(
                case_id=config.case_id,
                character_id=cid,
                character=char.model_copy(deep=True),
                private_facts=private_facts,
                unrelated_secrets=unrelated_secrets,
                known_secret_ids=known_secret_ids,
                cover_story=cover_story,
            )

        t1_session = T1Session(
            session_id=f"sess_{config.case_id}_{config.seed}",
            case_id=config.case_id,
            current_turn=0,
            discovered_facts=t1_facts,
            recorded_claims=initial_claims,
            contradiction_flags=[],
            revealed_edges=revealed_edges,
        )

        return t1_session, t2_knowledge

