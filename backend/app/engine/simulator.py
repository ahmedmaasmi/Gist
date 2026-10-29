# backend/app/engine/simulator.py
import hashlib
import json
import random
from typing import Optional

from app.domain.character import (
    Character,
    CharacterSecret,
    RelationshipEdge,
    RelationshipGraph,
)
from app.domain.enums import (
    EvidenceCategory,
    GoalType,
    InteractionType,
    ProvenanceClass,
    VerificationStatus,
)
from app.domain.setting import SettingTemplate
from app.domain.simulation import SimulatedCaseBundle
from app.domain.tiers import T0Public, T3Canonical
from app.domain.world import CanonicalEvent, Fact, SimulationConfig, TimeInterval
from app.engine.observation import ObservationModel


class SocialSimulator:
    """
    PRD Section 7A.1–7A.6, Section 8.2, and Requirements CH-01, CH-02, CH-03:
    Deterministic tick-based social simulation engine using an isolated
    `random.Random(config.seed)` instance with zero global RNG state and
    zero character-specific branches.
    """

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        setting: Optional[SettingTemplate] = None,
        characters: Optional[list[Character]] = None,
        relationship_graph: Optional[RelationshipGraph] = None,
    ) -> None:
        self.config = config
        self.setting = setting
        self.characters = characters
        self.relationship_graph = relationship_graph

    @staticmethod
    def compute_log_hash(canonical_events: list[CanonicalEvent]) -> str:
        """
        PRD 7A.4: Serializes canonical_events to canonical JSON (sort_keys=True)
        and returns its SHA-256 hex digest.
        """
        serialized = json.dumps(
            [event.model_dump(mode="json") for event in canonical_events],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _get_planned_location(
        character: Character,
        tick_min: int,
        default_loc_id: str,
    ) -> str:
        """
        Determines a character's planned location at `tick_min` from their `ScheduleSlot` list.
        """
        for slot in character.schedule:
            if slot.time_interval.start_min <= tick_min < slot.time_interval.end_min:
                return slot.planned_location_id
        for slot in character.schedule:
            if slot.time_interval.start_min <= tick_min <= slot.time_interval.end_min:
                return slot.planned_location_id
        return default_loc_id

    @staticmethod
    def _ensure_directed_edge(
        graph: RelationshipGraph,
        source_id: str,
        target_id: str,
    ) -> RelationshipEdge:
        """Returns existing directed edge source_id -> target_id, or creates a neutral one."""
        edge = graph.get_edge(source_id, target_id)
        if edge is None:
            edge = RelationshipEdge(
                source_id=source_id,
                target_id=target_id,
                affinity=0.0,
                trust=0.3,
                obligation=0.0,
            )
            graph.edges.append(edge)
        return edge

    @classmethod
    def _score_suspect_for_culprit(
        cls,
        suspect: Character,
        config: SimulationConfig,
        setting: SettingTemplate,
        graph: RelationshipGraph,
        pre_murder_events: list[CanonicalEvent],
        murder_ticks: list[int],
        default_loc_id: str,
    ) -> tuple[float, float, float, float]:
        """
        PRD 7A.4: Scores a non-victim suspect by:
        - motive_score: crime-linked secrets, goals targeting victim, negative affinity toward victim, ARGUE events with victim
        - opportunity_score: share of murder_window where suspect is in or within travel time of crime_location_id
        - low_composure_score: (1.0 - traits.composure) + traits.temper * 0.5
        Returns (total_score, motive_score, opportunity_score, low_composure_score).
        """
        # 1. Motive score
        crime_secret_score = sum(
            s.severity for s in suspect.secrets if s.is_crime_linked
        )
        victim_goal_score = sum(
            0.45
            for g in suspect.goals
            if g.target_character_id == config.victim_id
        )
        edge_to_victim = graph.get_edge(suspect.character_id, config.victim_id)
        neg_affinity_score = (
            abs(edge_to_victim.affinity) * 0.5
            if (edge_to_victim is not None and edge_to_victim.affinity < 0.0)
            else 0.0
        )
        argue_with_victim_count = sum(
            1
            for ev in pre_murder_events
            if ev.event_kind == "INTERACTION"
            and ev.interaction_type == InteractionType.ARGUE
            and (
                (ev.actor_id == suspect.character_id and ev.target_id == config.victim_id)
                or (ev.actor_id == config.victim_id and ev.target_id == suspect.character_id)
            )
        )
        argue_score = argue_with_victim_count * 0.35
        motive_score = (
            crime_secret_score + victim_goal_score + neg_affinity_score + argue_score
        )

        # 2. Opportunity score across murder_window
        window_duration = max(config.tick_size_min, config.murder_window.duration)
        if not murder_ticks:
            opportunity_score = 0.5
        else:
            tick_Reach_scores: list[float] = []
            for t in murder_ticks:
                planned_loc = cls._get_planned_location(suspect, t, default_loc_id)
                if planned_loc == config.crime_location_id:
                    tick_Reach_scores.append(1.0)
                else:
                    travel_min = setting.get_travel_time(
                        planned_loc, config.crime_location_id
                    )
                    if travel_min <= window_duration:
                        reach = max(0.1, 1.0 - (travel_min / (window_duration + 1.0)))
                        tick_Reach_scores.append(reach)
                    else:
                        tick_Reach_scores.append(0.0)
            opportunity_score = sum(tick_Reach_scores) / len(tick_Reach_scores)

        # 3. Low-composure score: (1.0 - traits.composure) + traits.temper * 0.5
        low_composure_score = (1.0 - suspect.traits.composure) + (
            suspect.traits.temper * 0.5
        )

        total_score = motive_score + opportunity_score + low_composure_score
        return total_score, motive_score, opportunity_score, low_composure_score

    def simulate(
        self,
        setting: Optional[SettingTemplate] = None,
        characters: Optional[list[Character]] = None,
        relationship_graph: Optional[RelationshipGraph] = None,
        config: Optional[SimulationConfig] = None,
    ) -> SimulatedCaseBundle:
        """
        Executes the full tick-based social simulation and derives T0, T1, T2, and T3.
        """
        cfg = (config or self.config)
        if cfg is None:
            raise ValueError("SimulationConfig must be provided to SocialSimulator.")
        cfg = cfg.model_copy(deep=True)

        tpl = (setting or self.setting)
        if tpl is None:
            raise ValueError("SettingTemplate must be provided to SocialSimulator.")
        tpl = tpl.model_copy(deep=True)

        raw_chars = characters if characters is not None else self.characters
        if not raw_chars:
            raise ValueError("A non-empty list of Characters must be provided to SocialSimulator.")
        chars = sorted(
            [c.model_copy(deep=True) for c in raw_chars],
            key=lambda c: c.character_id,
        )

        raw_graph = (
            relationship_graph
            if relationship_graph is not None
            else (self.relationship_graph or RelationshipGraph())
        )
        graph = raw_graph.model_copy(deep=True)

        # CH-03: Isolated seeded RNG instance; zero global RNG state
        rng = random.Random(cfg.seed)

        default_loc_id = (
            tpl.locations[0].location_id if tpl.locations else cfg.crime_location_id
        )
        restricted_locs = {
            loc.location_id for loc in tpl.locations if loc.is_restricted
        }

        all_ticks = list(
            range(cfg.start_min, cfg.end_min + 1, cfg.tick_size_min)
        )
        if not all_ticks:
            all_ticks = [cfg.start_min]

        murder_ticks = [
            t
            for t in all_ticks
            if cfg.murder_window.start_min <= t <= cfg.murder_window.end_min
        ]
        if not murder_ticks:
            murder_ticks = [cfg.murder_window.start_min]

        # Select murder_tick inside murder_window (prefer midpoint or second tick so pre-murder ticks exist)
        if len(murder_ticks) > 1 and murder_ticks[0] == all_ticks[0]:
            murder_tick = murder_ticks[len(murder_ticks) // 2]
        else:
            murder_tick = murder_ticks[len(murder_ticks) // 2]

        canonical_events: list[CanonicalEvent] = []
        event_counter = 0

        def next_event_id(kind: str, tick: int) -> str:
            nonlocal event_counter
            event_counter += 1
            return f"evt_{cfg.case_id}_{kind.lower()}_{tick}_{event_counter:03d}"

        last_location: dict[str, str] = {}
        argued_pairs: set[tuple[str, str]] = set()
        confided_secrets: set[tuple[str, str, str]] = set()  # (actor_id, target_id, secret_id)
        cover_pledged_pairs: set[tuple[str, str]] = set()

        # Precompute last pre-murder co-located tick for each ordered pair (char_a, char_b)
        pre_murder_ticks = [t for t in all_ticks if t < murder_tick]
        if not pre_murder_ticks:
            pre_murder_ticks = [murder_tick]

        last_colocated_pre_murder_tick: dict[tuple[str, str], int] = {}
        for t in pre_murder_ticks:
            loc_bucket: dict[str, list[str]] = {}
            for c in chars:
                loc = self._get_planned_location(c, t, default_loc_id)
                loc_bucket.setdefault(loc, []).append(c.character_id)
            for members in loc_bucket.values():
                for id_a in members:
                    for id_b in members:
                        if id_a != id_b:
                            last_colocated_pre_murder_tick[(id_a, id_b)] = t

        victim_alive = True
        murder_executed = False
        culprit_id: Optional[str] = None
        culprit_scores: dict[str, tuple[float, float, float, float]] = {}

        conflicting_goal_types = {
            GoalType.REVENGE,
            GoalType.MONEY,
            GoalType.INHERITANCE,
            GoalType.HIDE_SECRET,
        }

        for tick_min in all_ticks:
            alive_chars = [
                c
                for c in chars
                if victim_alive or c.character_id != cfg.victim_id
            ]

            # Determine planned location for each alive character
            planned_locations: dict[str, str] = {
                c.character_id: self._get_planned_location(c, tick_min, default_loc_id)
                for c in alive_chars
            }

            # Evaluate pre-murder interactions if murder has not yet occurred
            # (If start_min == murder_tick, pre-murder interactions still run before murder execution)
            if not murder_executed and tick_min <= murder_tick:
                colocated_groups: dict[str, list[Character]] = {}
                for c in alive_chars:
                    loc_id = planned_locations[c.character_id]
                    colocated_groups.setdefault(loc_id, []).append(c)

                # If tick_min < murder_tick (or single-tick window), record pre-murder movements and interactions
                if tick_min < murder_tick or len(all_ticks) == 1:
                    for loc_id in sorted(colocated_groups.keys()):
                        group = colocated_groups[loc_id]
                        for c in group:
                            cid = c.character_id
                            prev_loc = last_location.get(cid)
                            in_window = (
                                cfg.murder_window.start_min
                                <= tick_min
                                <= cfg.murder_window.end_min
                            )
                            if prev_loc != loc_id or in_window or loc_id in restricted_locs:
                                witnesses = [
                                    other.character_id
                                    for other in group
                                    if other.character_id != cid
                                ]
                                move_roll = rng.random()
                                canonical_events.append(
                                    CanonicalEvent(
                                        event_id=next_event_id("MOVEMENT", tick_min),
                                        tick_min=tick_min,
                                        location_id=loc_id,
                                        actor_id=cid,
                                        target_id=None,
                                        interaction_type=None,
                                        event_kind="MOVEMENT",
                                        reason_string=(
                                            f"Scheduled movement at tick {tick_min}: {cid} at "
                                            f"'{loc_id}' (composure={c.traits.composure:.2f}, "
                                            f"secrecy={c.traits.secrecy:.2f}, roll={move_roll:.4f})."
                                        ),
                                        witness_ids=witnesses,
                                        metadata={
                                            "composure": round(c.traits.composure, 4),
                                            "secrecy": round(c.traits.secrecy, 4),
                                            "is_restricted": loc_id in restricted_locs,
                                            "rng_roll": round(move_roll, 6),
                                        },
                                    )
                                )
                                last_location[cid] = loc_id

                        # Evaluate v0.1 interactions for ordered co-located pairs (char_a, char_b)
                        for char_a in group:
                            for char_b in group:
                                if char_a.character_id == char_b.character_id:
                                    continue

                                pair_key = (char_a.character_id, char_b.character_id)
                                is_last_opportunity = (
                                    last_colocated_pre_murder_tick.get(pair_key) == tick_min
                                )
                                edge = self._ensure_directed_edge(
                                    graph, char_a.character_id, char_b.character_id
                                )
                                bystanders = [
                                    other.character_id
                                    for other in group
                                    if other.character_id
                                    not in (char_a.character_id, char_b.character_id)
                                ]

                                # 1. ARGUE (PRD 7A.3)
                                has_conflicting_goal = any(
                                    g.target_character_id == char_b.character_id
                                    and g.goal_type in conflicting_goal_types
                                    for g in char_a.goals
                                )
                                if (
                                    pair_key not in argued_pairs
                                    and char_a.traits.temper >= 0.5
                                    and (edge.affinity < 0.0 or has_conflicting_goal)
                                ):
                                    prob = max(
                                        0.0,
                                        min(
                                            1.0,
                                            char_a.traits.temper
                                            * (1.0 - edge.affinity)
                                            / 2.0,
                                        ),
                                    )
                                    roll = rng.random()
                                    if roll < prob or (is_last_opportunity and prob >= 0.25):
                                        old_affinity = edge.affinity
                                        edge.apply_delta(d_affinity=-0.2)
                                        argued_pairs.add(pair_key)
                                        canonical_events.append(
                                            CanonicalEvent(
                                                event_id=next_event_id(
                                                    "INTERACTION", tick_min
                                                ),
                                                tick_min=tick_min,
                                                location_id=loc_id,
                                                actor_id=char_a.character_id,
                                                target_id=char_b.character_id,
                                                interaction_type=InteractionType.ARGUE,
                                                event_kind="INTERACTION",
                                                reason_string=(
                                                    f"ARGUE at tick {tick_min}: "
                                                    f"actor={char_a.character_id} "
                                                    f"(temper={char_a.traits.temper:.2f}) argued with "
                                                    f"target={char_b.character_id} "
                                                    f"(prior_affinity={old_affinity:.2f}, "
                                                    f"new_affinity={edge.affinity:.2f}, "
                                                    f"conflicting_goal={has_conflicting_goal}, "
                                                    f"prob={prob:.2f}, roll={roll:.4f})."
                                                ),
                                                witness_ids=bystanders,
                                                metadata={
                                                    "temper": round(char_a.traits.temper, 4),
                                                    "prior_affinity": round(old_affinity, 4),
                                                    "new_affinity": round(edge.affinity, 4),
                                                    "probability": round(prob, 4),
                                                    "rng_roll": round(roll, 6),
                                                },
                                            )
                                        )

                                # 2. CONFIDE (PRD 7A.3)
                                unconfided = [
                                    s
                                    for s in char_a.secrets
                                    if (
                                        char_a.character_id,
                                        char_b.character_id,
                                        s.secret_id,
                                    )
                                    not in confided_secrets
                                ]
                                if edge.trust >= 0.6 and len(unconfided) > 0:
                                    prob = max(
                                        0.0,
                                        min(
                                            1.0,
                                            edge.trust * (1.0 - char_a.traits.secrecy),
                                        ),
                                    )
                                    roll = rng.random()
                                    if roll < prob or (is_last_opportunity and prob >= 0.15):
                                        sec = unconfided[0]
                                        old_trust = edge.trust
                                        edge.apply_delta(d_trust=0.15)
                                        confided_secrets.add(
                                            (
                                                char_a.character_id,
                                                char_b.character_id,
                                                sec.secret_id,
                                            )
                                        )
                                        canonical_events.append(
                                            CanonicalEvent(
                                                event_id=next_event_id(
                                                    "INTERACTION", tick_min
                                                ),
                                                tick_min=tick_min,
                                                location_id=loc_id,
                                                actor_id=char_a.character_id,
                                                target_id=char_b.character_id,
                                                interaction_type=InteractionType.CONFIDE,
                                                event_kind="INTERACTION",
                                                reason_string=(
                                                    f"CONFIDE at tick {tick_min}: "
                                                    f"actor={char_a.character_id} "
                                                    f"(secrecy={char_a.traits.secrecy:.2f}) confided "
                                                    f"secret='{sec.secret_id}' to "
                                                    f"target={char_b.character_id} "
                                                    f"(prior_trust={old_trust:.2f}, "
                                                    f"new_trust={edge.trust:.2f}, "
                                                    f"prob={prob:.2f}, roll={roll:.4f})."
                                                ),
                                                witness_ids=bystanders,
                                                metadata={
                                                    "secret_id": sec.secret_id,
                                                    "is_crime_linked": sec.is_crime_linked,
                                                    "secrecy": round(char_a.traits.secrecy, 4),
                                                    "prior_trust": round(old_trust, 4),
                                                    "new_trust": round(edge.trust, 4),
                                                    "probability": round(prob, 4),
                                                    "rng_roll": round(roll, 6),
                                                },
                                            )
                                        )

                                # 3. COVER_FOR (PRD 7A.3)
                                if (
                                    pair_key not in cover_pledged_pairs
                                    and char_b.character_id != cfg.victim_id
                                    and (
                                        edge.loyalty_or_trust >= 0.65
                                        or edge.obligation >= 0.6
                                    )
                                ):
                                    prob = max(edge.loyalty_or_trust, edge.obligation)
                                    roll = rng.random()
                                    if roll < prob or is_last_opportunity:
                                        cover_pledged_pairs.add(pair_key)
                                        canonical_events.append(
                                            CanonicalEvent(
                                                event_id=next_event_id(
                                                    "INTERACTION", tick_min
                                                ),
                                                tick_min=tick_min,
                                                location_id=loc_id,
                                                actor_id=char_a.character_id,
                                                target_id=char_b.character_id,
                                                interaction_type=InteractionType.COVER_FOR,
                                                event_kind="INTERACTION",
                                                reason_string=(
                                                    f"COVER_FOR at tick {tick_min}: "
                                                    f"target={char_b.character_id} pledged "
                                                    f"INTENTIONAL_LIE alibi cover for "
                                                    f"actor={char_a.character_id} "
                                                    f"(loyalty_or_trust={edge.loyalty_or_trust:.2f}, "
                                                    f"trust={edge.trust:.2f}, "
                                                    f"obligation={edge.obligation:.2f}, "
                                                    f"prob={prob:.2f}, roll={roll:.4f})."
                                                ),
                                                witness_ids=bystanders,
                                                metadata={
                                                    "pledge_type": "INTENTIONAL_LIE",
                                                    "intent": "INTENTIONAL_LIE",
                                                    "covered_character_id": char_a.character_id,
                                                    "covering_character_id": char_b.character_id,
                                                    "loyalty_or_trust": round(
                                                        edge.loyalty_or_trust, 4
                                                    ),
                                                    "obligation": round(edge.obligation, 4),
                                                    "rng_roll": round(roll, 6),
                                                },
                                            )
                                        )

            # Execute Culprit Selection & Murder at murder_tick
            if tick_min == murder_tick and not murder_executed:
                suspects = [c for c in chars if c.character_id != cfg.victim_id]
                for s in suspects:
                    culprit_scores[s.character_id] = self._score_suspect_for_culprit(
                        suspect=s,
                        config=cfg,
                        setting=tpl,
                        graph=graph,
                        pre_murder_events=canonical_events,
                        murder_ticks=murder_ticks,
                        default_loc_id=default_loc_id,
                    )

                if cfg.forced_culprit_id is not None:
                    culprit_id = cfg.forced_culprit_id
                else:
                    # Pick suspect with highest combined score (deterministic tie-break by character_id)
                    best_suspect = max(
                        suspects,
                        key=lambda s: (
                            round(culprit_scores[s.character_id][0], 6),
                            s.character_id,
                        ),
                    )
                    culprit_id = best_suspect.character_id

                culprit_char = next(
                    c for c in chars if c.character_id == culprit_id
                )
                tot_sc, mot_sc, opp_sc, comp_sc = culprit_scores[culprit_id]

                # Ensure at least one innocent suspect has a red-herring secret or suspicious movement (PRD 8.2)
                innocent_suspects = [
                    c
                    for c in chars
                    if c.character_id not in (cfg.victim_id, culprit_id)
                ]
                if innocent_suspects:
                    has_any_red_herring = any(
                        not sec.is_crime_linked
                        for inn in innocent_suspects
                        for sec in inn.secrets
                    )
                    if not has_any_red_herring:
                        chosen_innocent = innocent_suspects[
                            rng.randrange(len(innocent_suspects))
                        ]
                        chosen_innocent.secrets.append(
                            CharacterSecret(
                                secret_id=f"sec_red_herring_{chosen_innocent.character_id}",
                                description=(
                                    f"{chosen_innocent.name} is hiding an unrelated "
                                    f"clandestine meeting and personal debt."
                                ),
                                severity=0.55,
                                is_crime_linked=False,
                            )
                        )

                # Override culprit and victim locations to crime_location_id for murder_tick
                planned_culprit_loc = planned_locations.get(
                    culprit_id, default_loc_id
                )
                planned_locations[culprit_id] = cfg.crime_location_id
                planned_locations[cfg.victim_id] = cfg.crime_location_id

                # Record movements for all characters at murder_tick
                loc_groups_at_murder: dict[str, list[Character]] = {}
                for c in alive_chars:
                    loc_groups_at_murder.setdefault(
                        planned_locations[c.character_id], []
                    ).append(c)

                for loc_id in sorted(loc_groups_at_murder.keys()):
                    group = loc_groups_at_murder[loc_id]
                    for c in group:
                        cid = c.character_id
                        witnesses = [
                            other.character_id
                            for other in group
                            if other.character_id != cid
                            and other.character_id != cfg.victim_id
                        ]
                        move_roll = rng.random()
                        canonical_events.append(
                            CanonicalEvent(
                                event_id=next_event_id("MOVEMENT", tick_min),
                                tick_min=tick_min,
                                location_id=loc_id,
                                actor_id=cid,
                                target_id=None,
                                interaction_type=None,
                                event_kind="MOVEMENT",
                                reason_string=(
                                    f"Murder-window movement at tick {tick_min}: {cid} at "
                                    f"'{loc_id}' (planned='{planned_culprit_loc if cid == culprit_id else loc_id}', "
                                    f"composure={c.traits.composure:.2f}, temper={c.traits.temper:.2f}, "
                                    f"roll={move_roll:.4f})."
                                ),
                                witness_ids=witnesses,
                                metadata={
                                    "composure": round(c.traits.composure, 4),
                                    "temper": round(c.traits.temper, 4),
                                    "is_restricted": loc_id in restricted_locs,
                                    "is_culprit_override": cid == culprit_id,
                                    "rng_roll": round(move_roll, 6),
                                },
                            )
                        )
                        last_location[cid] = loc_id

                # Emit MURDER CanonicalEvent
                murder_roll = rng.random()
                canonical_events.append(
                    CanonicalEvent(
                        event_id=next_event_id("MURDER", tick_min),
                        tick_min=tick_min,
                        location_id=cfg.crime_location_id,
                        actor_id=culprit_id,
                        target_id=cfg.victim_id,
                        interaction_type=None,
                        event_kind="MURDER",
                        reason_string=(
                            f"MURDER at tick {tick_min} in '{cfg.crime_location_id}': "
                            f"culprit={culprit_id} killed victim={cfg.victim_id} "
                            f"[total_score={tot_sc:.3f}, motive_score={mot_sc:.3f}, "
                            f"opportunity_score={opp_sc:.3f}, low_composure_score={comp_sc:.3f}, "
                            f"temper={culprit_char.traits.temper:.2f}, "
                            f"composure={culprit_char.traits.composure:.2f}, "
                            f"forced={cfg.forced_culprit_id is not None}]."
                        ),
                        witness_ids=[],
                        metadata={
                            "total_score": round(tot_sc, 4),
                            "motive_score": round(mot_sc, 4),
                            "opportunity_score": round(opp_sc, 4),
                            "low_composure_score": round(comp_sc, 4),
                            "temper": round(culprit_char.traits.temper, 4),
                            "composure": round(culprit_char.traits.composure, 4),
                            "forced": cfg.forced_culprit_id is not None,
                            "rng_roll": round(murder_roll, 6),
                        },
                    )
                )

                victim_alive = False
                murder_executed = True
                continue

            # Post-murder tick movements for surviving characters
            if murder_executed and tick_min > murder_tick:
                post_groups: dict[str, list[Character]] = {}
                for c in alive_chars:
                    post_groups.setdefault(
                        planned_locations[c.character_id], []
                    ).append(c)

                for loc_id in sorted(post_groups.keys()):
                    group = post_groups[loc_id]
                    for c in group:
                        cid = c.character_id
                        prev_loc = last_location.get(cid)
                        in_window = (
                            cfg.murder_window.start_min
                            <= tick_min
                            <= cfg.murder_window.end_min
                        )
                        if prev_loc != loc_id or in_window or loc_id in restricted_locs:
                            witnesses = [
                                other.character_id
                                for other in group
                                if other.character_id != cid
                            ]
                            move_roll = rng.random()
                            canonical_events.append(
                                CanonicalEvent(
                                    event_id=next_event_id("MOVEMENT", tick_min),
                                    tick_min=tick_min,
                                    location_id=loc_id,
                                    actor_id=cid,
                                    target_id=None,
                                    interaction_type=None,
                                    event_kind="MOVEMENT",
                                    reason_string=(
                                        f"Post-murder movement at tick {tick_min}: {cid} at "
                                        f"'{loc_id}' (composure={c.traits.composure:.2f}, "
                                        f"secrecy={c.traits.secrecy:.2f}, roll={move_roll:.4f})."
                                    ),
                                    witness_ids=witnesses,
                                    metadata={
                                        "composure": round(c.traits.composure, 4),
                                        "secrecy": round(c.traits.secrecy, 4),
                                        "is_restricted": loc_id in restricted_locs,
                                        "rng_roll": round(move_roll, 6),
                                    },
                                )
                            )
                            last_location[cid] = loc_id

        assert culprit_id is not None, "Simulation must select a culprit_id."

        log_hash = self.compute_log_hash(canonical_events)
        canary_token = f"CANARY_T3_{cfg.case_id}_{cfg.seed}"

        t0_public = T0Public(
            case_id=cfg.case_id,
            title=f"Case {cfg.case_id} at {tpl.name}",
            victim_id=cfg.victim_id,
            crime_location_id=cfg.crime_location_id,
            crime_window=cfg.murder_window,
            suspect_ids=[
                c.character_id for c in chars if c.character_id != cfg.victim_id
            ],
        )

        ground_truth_facts = [
            Fact(
                fact_id=f"t3_gt_{cfg.case_id}_murder",
                case_id=cfg.case_id,
                description=(
                    f"[{canary_token}] Ground truth: {culprit_id} murdered "
                    f"{cfg.victim_id} in {cfg.crime_location_id} at tick {murder_tick}."
                ),
                subject_id=culprit_id,
                target_id=cfg.victim_id,
                location_id=cfg.crime_location_id,
                time_interval=cfg.murder_window,
                category=EvidenceCategory.FORENSIC,
                provenance=ProvenanceClass.PHYSICAL,
                reliability=1.0,
                status=VerificationStatus.ESTABLISHED,
            )
        ]

        t3_canonical = T3Canonical(
            case_id=cfg.case_id,
            culprit_id=culprit_id,
            crime_location_id=cfg.crime_location_id,
            crime_window=cfg.murder_window,
            ground_truth_facts=ground_truth_facts,
            canonical_events=canonical_events,
            relationship_graph=graph,
            canary_token=canary_token,
        )

        t1_session, t2_knowledge = ObservationModel.derive(
            config=cfg,
            setting=tpl,
            characters=chars,
            relationship_graph=graph,
            canonical_events=canonical_events,
            t3_canonical=t3_canonical,
            rng=rng,
        )

        return SimulatedCaseBundle(
            config=cfg,
            t0_public=t0_public,
            t1_session=t1_session,
            t2_knowledge=t2_knowledge,
            t3_canonical=t3_canonical,
            canonical_events=canonical_events,
            log_hash=log_hash,
        )

    # Alias for convenience
    run = simulate

