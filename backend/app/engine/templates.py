# backend/app/engine/templates.py
import json
import random
from pathlib import Path
from typing import Iterator, Optional
from pydantic import BaseModel

from app.domain.character import (
    Character,
    CharacterGoal,
    CharacterSecret,
    CharacterTraits,
    RelationshipEdge,
    RelationshipGraph,
    ScheduleSlot,
)
from app.domain.enums import GoalType, RelationshipTag
from app.domain.setting import VALID_SPLIT_GROUPS, SettingTemplate
from app.domain.simulation import SimulatedCaseBundle
from app.domain.world import SimulationConfig, TimeInterval
from app.engine.simulator import SocialSimulator
from app.engine.solver import CaseSolvabilityValidator, CaseValidationReport


DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "data" / "templates"

FIRST_NAMES = (
    "Evelyn",
    "Marcus",
    "Clara",
    "Julian",
    "Helena",
    "Victor",
    "Simone",
    "Arthur",
    "Nadia",
    "Soren",
    "Beatrice",
    "Damon",
    "Lydia",
    "Gideon",
)

LAST_NAMES = (
    "Vance",
    "Reed",
    "Mercer",
    "Cross",
    "Sterling",
    "Thorne",
    "Kestrel",
    "Ashford",
    "Locke",
    "Sinclair",
    "Harrow",
    "Kovac",
    "Duval",
    "Falk",
)

VOICE_NOTES_POOL = (
    "Clipped, formal cadence; avoids contractions when defensive.",
    "Measured and bureaucratic; cites schedules and procedures.",
    "Warm but guarded; deflects personal questions with dry humour.",
    "Restless and sharp-tongued; speaks in short, impatient sentences.",
    "Soft-spoken and observant; pauses before answering direct accusations.",
    "Polished and patrician; masks anxiety behind condescension.",
    "Pragmatic and blunt; focuses on financial and logistical details.",
)


class SampledCaseSetup(BaseModel):
    """
    Procedural case setup sampled from a SettingTemplate.
    Supports both attribute access (.setting, .characters, .relationship_graph, .config)
    and tuple unpacking (characters, relationship_graph, config).
    """
    setting: SettingTemplate
    characters: list[Character]
    relationship_graph: RelationshipGraph
    config: SimulationConfig

    def __iter__(self) -> Iterator[object]:
        """Allows unpacking: `characters, relationship_graph, config = sample_case_setup_from_template(...)`."""
        yield self.characters
        yield self.relationship_graph
        yield self.config

    def simulate(self) -> SimulatedCaseBundle:
        """Convenience helper to run SocialSimulator on this sampled setup."""
        simulator = SocialSimulator(
            config=self.config,
            setting=self.setting,
            characters=self.characters,
            relationship_graph=self.relationship_graph,
        )
        return simulator.simulate()


class TemplateRegistry:
    """
    PRD Section 7B.2, 8.1, and 8.4:
    Loads, validates, and queries the 8 structural setting templates from `data/templates/`.
    """
    _cache: Optional[dict[str, SettingTemplate]] = None

    @classmethod
    def load_all_templates(
        cls,
        templates_dir: Optional[Path | str] = None,
        force_reload: bool = False,
    ) -> dict[str, SettingTemplate]:
        """
        Loads and validates all JSON setting templates from `data/templates/`.
        Returns a dictionary keyed by `template_id` in deterministic sorted order.
        """
        if cls._cache is not None and templates_dir is None and not force_reload:
            return {k: v.model_copy(deep=True) for k, v in cls._cache.items()}

        target_dir = Path(templates_dir) if templates_dir is not None else DEFAULT_TEMPLATES_DIR
        if not target_dir.exists() or not target_dir.is_dir():
            raise FileNotFoundError(f"Templates directory not found at '{target_dir}'.")

        templates: dict[str, SettingTemplate] = {}
        for json_path in sorted(target_dir.glob("*.json")):
            raw_data = json.loads(json_path.read_text(encoding="utf-8"))
            template = SettingTemplate.model_validate(raw_data)
            if template.template_id in templates:
                raise ValueError(
                    f"Duplicate template_id '{template.template_id}' found in '{json_path.name}'."
                )
            templates[template.template_id] = template

        if templates_dir is None:
            cls._cache = templates

        return {k: v.model_copy(deep=True) for k, v in templates.items()}

    @classmethod
    def get_template(
        cls,
        template_id: str,
        templates_dir: Optional[Path | str] = None,
    ) -> SettingTemplate:
        """
        Returns a validated `SettingTemplate` by `template_id` (e.g. 'manor' or 'tpl_manor').
        """
        templates = cls.load_all_templates(templates_dir=templates_dir)
        if template_id in templates:
            return templates[template_id]
        normalized = template_id.removeprefix("tpl_").removesuffix(".json")
        if normalized in templates:
            return templates[normalized]
        raise KeyError(
            f"Unknown template_id '{template_id}'. Available templates: {sorted(templates.keys())}"
        )

    @classmethod
    def get_templates_by_split(
        cls,
        split_group: str,
        templates_dir: Optional[Path | str] = None,
    ) -> list[SettingTemplate]:
        """
        Returns all templates assigned to `split_group` ('train', 'val', or 'test_held_out_template').
        """
        if split_group not in VALID_SPLIT_GROUPS:
            raise ValueError(
                f"Invalid split_group '{split_group}'. Expected one of {sorted(VALID_SPLIT_GROUPS)}."
            )
        templates = cls.load_all_templates(templates_dir=templates_dir)
        return [
            tpl
            for tpl in templates.values()
            if tpl.split_group == split_group
        ]


def load_all_templates(
    templates_dir: Optional[Path | str] = None,
    force_reload: bool = False,
) -> dict[str, SettingTemplate]:
    """Module-level wrapper for TemplateRegistry.load_all_templates()."""
    return TemplateRegistry.load_all_templates(
        templates_dir=templates_dir,
        force_reload=force_reload,
    )


def get_template(
    template_id: str,
    templates_dir: Optional[Path | str] = None,
) -> SettingTemplate:
    """Module-level wrapper for TemplateRegistry.get_template()."""
    return TemplateRegistry.get_template(
        template_id=template_id,
        templates_dir=templates_dir,
    )


def get_templates_by_split(
    split_group: str,
    templates_dir: Optional[Path | str] = None,
) -> list[SettingTemplate]:
    """Module-level wrapper for TemplateRegistry.get_templates_by_split()."""
    return TemplateRegistry.get_templates_by_split(
        split_group=split_group,
        templates_dir=templates_dir,
    )


def _sample_trait_value(
    rng: random.Random,
    low: float,
    high: float,
    ood_mode: bool = False,
) -> float:
    """
    Samples a trait value inside [low, high] subset of [0.1, 0.9] when ood_mode=False,
    or intentionally outside [0.1, 0.9] when ood_mode=True to test CH-04 / CL-05.
    """
    if ood_mode:
        if rng.random() < 0.5:
            return round(rng.uniform(0.0, 0.08), 2)
        return round(rng.uniform(0.92, 1.0), 2)
    clamped_low = max(0.10, min(0.90, low))
    clamped_high = max(clamped_low, min(0.90, high))
    return round(rng.uniform(clamped_low, clamped_high), 2)


def sample_case_setup_from_template(
    template: SettingTemplate,
    seed: int,
    num_suspects: int = 4,
    ood_mode: bool = False,
) -> SampledCaseSetup:
    """
    PRD Section 7B.2, 7B.4 (CL-06), 8.2, and CH-03/CH-04:
    Procedurally samples a complete case setup (characters, schedules, secrets, goals,
    asymmetric RelationshipGraph, and SimulationConfig) from a `SettingTemplate`
    using an isolated `random.Random(seed)` instance.
    """
    if num_suspects < 3 or num_suspects > 6:
        raise ValueError(
            f"CL-06 Violation: num_suspects must be between 3 and 6 (got {num_suspects})."
        )

    rng = random.Random(seed)
    tpl = template.model_copy(deep=True)

    # 1. Select crime location and social/alibi hubs
    crime_location_id = tpl.default_crime_location_ids[
        rng.randrange(len(tpl.default_crime_location_ids))
    ]
    unrestricted_locs = [
        loc.location_id
        for loc in tpl.locations
        if not loc.is_restricted and loc.location_id != crime_location_id
    ]
    if not unrestricted_locs:
        unrestricted_locs = [
            loc.location_id
            for loc in tpl.locations
            if loc.location_id != crime_location_id
        ]

    # Sort unrestricted locations by travel time to crime_location_id so primary hub is close
    unrestricted_by_proximity = sorted(
        unrestricted_locs,
        key=lambda lid: (tpl.get_travel_time(lid, crime_location_id), lid),
    )
    social_hub_loc = unrestricted_by_proximity[0]
    secondary_hub_loc = (
        unrestricted_by_proximity[1]
        if len(unrestricted_by_proximity) > 1
        else social_hub_loc
    )
    distant_unrestricted_loc = unrestricted_by_proximity[-1]

    other_restricted_locs = [
        loc.location_id
        for loc in tpl.locations
        if loc.is_restricted and loc.location_id != crime_location_id
    ]

    # 2. Sample distinct names and occupations for (1 victim + num_suspects suspects)
    total_chars = num_suspects + 1
    first_pool = list(FIRST_NAMES)
    last_pool = list(LAST_NAMES)
    rng.shuffle(first_pool)
    rng.shuffle(last_pool)

    occupations = list(tpl.archetype_occupations) or [
        "Executive",
        "Consultant",
        "Physician",
        "Legal Counsel",
        "Archivist",
        "Operations Director",
        "Private Collector",
    ]
    rng.shuffle(occupations)

    victim_id = "victim_01"
    victim_name = f"{first_pool[0]} {last_pool[0]}"
    victim_occupation = occupations[0]

    victim_traits = CharacterTraits(
        temper=_sample_trait_value(rng, 0.45, 0.75, ood_mode=ood_mode),
        greed=_sample_trait_value(rng, 0.50, 0.85, ood_mode=ood_mode),
        loyalty=_sample_trait_value(rng, 0.30, 0.65, ood_mode=ood_mode),
        honesty=_sample_trait_value(rng, 0.40, 0.75, ood_mode=ood_mode),
        composure=_sample_trait_value(rng, 0.45, 0.80, ood_mode=ood_mode),
        secrecy=_sample_trait_value(rng, 0.55, 0.85, ood_mode=ood_mode),
    )

    victim_schedule = [
        ScheduleSlot(
            time_interval=TimeInterval(start_min=1080, end_min=1240),
            planned_location_id=social_hub_loc,
        ),
        ScheduleSlot(
            time_interval=TimeInterval(start_min=1240, end_min=1440),
            planned_location_id=crime_location_id,
        ),
    ]

    victim_char = Character(
        character_id=victim_id,
        name=victim_name,
        occupation=victim_occupation,
        voice_notes=VOICE_NOTES_POOL[0],
        traits=victim_traits,
        goals=[],
        secrets=[],
        schedule=victim_schedule,
    )

    # Choose role archetypes among suspects so every seed produces rich social dynamics
    primary_idx = rng.randrange(num_suspects)
    red_herring_idx = (primary_idx + 1) % num_suspects
    ally_idx = (primary_idx + 2) % num_suspects

    suspect_chars: list[Character] = []
    for idx in range(num_suspects):
        suspect_id = f"suspect_{idx + 1:02d}"
        full_name = f"{first_pool[(idx + 1) % len(first_pool)]} {last_pool[(idx + 1) % len(last_pool)]}"
        occ = occupations[(idx + 1) % len(occupations)]
        voice = VOICE_NOTES_POOL[(idx + 1) % len(VOICE_NOTES_POOL)]

        if idx == primary_idx:
            # Primary culprit candidate: high temper, low composure, strong motive & opportunity
            traits = CharacterTraits(
                temper=_sample_trait_value(rng, 0.72, 0.88, ood_mode=ood_mode),
                greed=_sample_trait_value(rng, 0.62, 0.88, ood_mode=ood_mode),
                loyalty=_sample_trait_value(rng, 0.15, 0.45, ood_mode=ood_mode),
                honesty=_sample_trait_value(rng, 0.15, 0.40, ood_mode=ood_mode),
                composure=_sample_trait_value(rng, 0.12, 0.28, ood_mode=ood_mode),
                secrecy=_sample_trait_value(rng, 0.55, 0.85, ood_mode=ood_mode),
            )
            motive_goal_type = rng.choice(
                [GoalType.REVENGE, GoalType.INHERITANCE, GoalType.HIDE_SECRET]
            )
            goals = [
                CharacterGoal(
                    goal_type=motive_goal_type,
                    target_character_id=victim_id,
                    description=(
                        f"{full_name} seeks {motive_goal_type.value.lower()} against "
                        f"{victim_name} over a critical dispute at {tpl.name}."
                    ),
                )
            ]
            secrets = [
                CharacterSecret(
                    secret_id=f"sec_{suspect_id}_crime",
                    description=(
                        f"{full_name} was about to be exposed by {victim_name} for "
                        f"fraudulent dealings at {tpl.name}."
                    ),
                    severity=round(rng.uniform(0.78, 0.90), 2),
                    is_crime_linked=True,
                )
            ]
            schedule = [
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1080, end_min=1250),
                    planned_location_id=social_hub_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1250, end_min=1310),
                    planned_location_id=social_hub_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1310, end_min=1440),
                    planned_location_id=secondary_hub_loc,
                ),
            ]
        elif idx == red_herring_idx:
            # Innocent red-herring suspect: has an unrelated secret + secondary motive
            traits = CharacterTraits(
                temper=_sample_trait_value(rng, 0.50, 0.68, ood_mode=ood_mode),
                greed=_sample_trait_value(rng, 0.40, 0.75, ood_mode=ood_mode),
                loyalty=_sample_trait_value(rng, 0.55, 0.85, ood_mode=ood_mode),
                honesty=_sample_trait_value(rng, 0.45, 0.78, ood_mode=ood_mode),
                composure=_sample_trait_value(rng, 0.60, 0.86, ood_mode=ood_mode),
                secrecy=_sample_trait_value(rng, 0.15, 0.35, ood_mode=ood_mode),
            )
            goals = [
                CharacterGoal(
                    goal_type=GoalType.MONEY,
                    target_character_id=victim_id,
                    description=(
                        f"{full_name} had an unresolved contract negotiation with {victim_name}."
                    ),
                )
            ]
            secrets = [
                CharacterSecret(
                    secret_id=f"sec_{suspect_id}_red_herring",
                    description=(
                        f"{full_name} is concealing an unrelated regulatory infraction and "
                        f"private meeting at {secondary_hub_loc}."
                    ),
                    severity=round(rng.uniform(0.50, 0.70), 2),
                    is_crime_linked=False,
                )
            ]
            pre_loc = other_restricted_locs[0] if other_restricted_locs else secondary_hub_loc
            schedule = [
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1080, end_min=1160),
                    planned_location_id=pre_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1160, end_min=1250),
                    planned_location_id=secondary_hub_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1250, end_min=1320),
                    planned_location_id=secondary_hub_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1320, end_min=1440),
                    planned_location_id=distant_unrestricted_loc,
                ),
            ]
        elif idx == ally_idx:
            # Bystander witness to the pre-murder argument & confidant/alibi-cover for red herring
            traits = CharacterTraits(
                temper=_sample_trait_value(rng, 0.20, 0.48, ood_mode=ood_mode),
                greed=_sample_trait_value(rng, 0.20, 0.55, ood_mode=ood_mode),
                loyalty=_sample_trait_value(rng, 0.65, 0.88, ood_mode=ood_mode),
                honesty=_sample_trait_value(rng, 0.55, 0.85, ood_mode=ood_mode),
                composure=_sample_trait_value(rng, 0.62, 0.88, ood_mode=ood_mode),
                secrecy=_sample_trait_value(rng, 0.30, 0.65, ood_mode=ood_mode),
            )
            goals = [
                CharacterGoal(
                    goal_type=GoalType.PROTECT_SOMEONE,
                    target_character_id=f"suspect_{red_herring_idx + 1:02d}",
                    description=(
                        f"{full_name} wants to shield suspect_{red_herring_idx + 1:02d} "
                        f"from professional scandal."
                    ),
                )
            ]
            secrets = []
            schedule = [
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1080, end_min=1160),
                    planned_location_id=social_hub_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1160, end_min=1250),
                    planned_location_id=secondary_hub_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1250, end_min=1320),
                    planned_location_id=distant_unrestricted_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1320, end_min=1440),
                    planned_location_id=social_hub_loc,
                ),
            ]
        else:
            # Additional innocent suspects (for 4, 5, or 6 suspect casts)
            traits = CharacterTraits(
                temper=_sample_trait_value(rng, 0.18, 0.55, ood_mode=ood_mode),
                greed=_sample_trait_value(rng, 0.20, 0.65, ood_mode=ood_mode),
                loyalty=_sample_trait_value(rng, 0.30, 0.75, ood_mode=ood_mode),
                honesty=_sample_trait_value(rng, 0.50, 0.88, ood_mode=ood_mode),
                composure=_sample_trait_value(rng, 0.58, 0.88, ood_mode=ood_mode),
                secrecy=_sample_trait_value(rng, 0.25, 0.70, ood_mode=ood_mode),
            )
            goals = [
                CharacterGoal(
                    goal_type=GoalType.HIDE_SECRET,
                    target_character_id=None,
                    description=f"{full_name} wants to avoid scrutiny during the investigation.",
                )
            ]
            secrets = [
                CharacterSecret(
                    secret_id=f"sec_{suspect_id}_minor",
                    description=f"{full_name} was conducting unauthorized side business.",
                    severity=round(rng.uniform(0.30, 0.55), 2),
                    is_crime_linked=False,
                )
            ]
            alt_loc = (
                other_restricted_locs[idx % len(other_restricted_locs)]
                if other_restricted_locs and idx % 2 == 1
                else distant_unrestricted_loc
            )
            schedule = [
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1080, end_min=1180),
                    planned_location_id=distant_unrestricted_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1180, end_min=1300),
                    planned_location_id=alt_loc,
                ),
                ScheduleSlot(
                    time_interval=TimeInterval(start_min=1300, end_min=1440),
                    planned_location_id=secondary_hub_loc,
                ),
            ]

        suspect_chars.append(
            Character(
                character_id=suspect_id,
                name=full_name,
                occupation=occ,
                voice_notes=voice,
                traits=traits,
                goals=goals,
                secrets=secrets,
                schedule=schedule,
            )
        )

    characters: list[Character] = [victim_char, *suspect_chars]

    # 3. Build asymmetric RelationshipGraph
    primary_id = f"suspect_{primary_idx + 1:02d}"
    red_herring_id = f"suspect_{red_herring_idx + 1:02d}"
    ally_id = f"suspect_{ally_idx + 1:02d}"

    edges: list[RelationshipEdge] = [
        # Primary suspect <-> Victim: strong hostility (asymmetric)
        RelationshipEdge(
            source_id=primary_id,
            target_id=victim_id,
            affinity=round(rng.uniform(-0.85, -0.55), 2),
            trust=round(rng.uniform(0.05, 0.25), 2),
            loyalty=0.10,
            obligation=round(rng.uniform(0.55, 0.85), 2),
            tags=[RelationshipTag.RIVAL],
            is_revealed_to_player=False,
        ),
        RelationshipEdge(
            source_id=victim_id,
            target_id=primary_id,
            affinity=round(rng.uniform(-0.45, -0.20), 2),
            trust=round(rng.uniform(0.15, 0.35), 2),
            loyalty=0.15,
            obligation=0.10,
            tags=[RelationshipTag.BUSINESS_PARTNER],
            is_revealed_to_player=False,
        ),
        # Red herring <-> Ally: high trust & loyalty/obligation (triggers CONFIDE and COVER_FOR)
        RelationshipEdge(
            source_id=red_herring_id,
            target_id=ally_id,
            affinity=round(rng.uniform(0.55, 0.85), 2),
            trust=round(rng.uniform(0.72, 0.90), 2),
            loyalty=round(rng.uniform(0.70, 0.88), 2),
            obligation=round(rng.uniform(0.65, 0.85), 2),
            tags=[RelationshipTag.SECRET_AFFAIR],
            is_revealed_to_player=False,
        ),
        RelationshipEdge(
            source_id=ally_id,
            target_id=red_herring_id,
            affinity=round(rng.uniform(0.45, 0.78), 2),
            trust=round(rng.uniform(0.68, 0.88), 2),
            loyalty=round(rng.uniform(0.68, 0.86), 2),
            obligation=round(rng.uniform(0.60, 0.80), 2),
            tags=[RelationshipTag.SECRET_AFFAIR],
            is_revealed_to_player=False,
        ),
        # Red herring -> Victim: mild tension
        RelationshipEdge(
            source_id=red_herring_id,
            target_id=victim_id,
            affinity=round(rng.uniform(-0.35, -0.10), 2),
            trust=round(rng.uniform(0.25, 0.50), 2),
            loyalty=0.25,
            obligation=round(rng.uniform(0.30, 0.55), 2),
            tags=[RelationshipTag.EMPLOYER_EMPLOYEE],
            is_revealed_to_player=False,
        ),
    ]

    # Add asymmetric background edges for remaining characters
    existing_pairs = {(e.source_id, e.target_id) for e in edges}
    for char_a in characters:
        for char_b in characters:
            if char_a.character_id == char_b.character_id:
                continue
            pair = (char_a.character_id, char_b.character_id)
            if pair in existing_pairs:
                continue
            if rng.random() < 0.45:
                edges.append(
                    RelationshipEdge(
                        source_id=char_a.character_id,
                        target_id=char_b.character_id,
                        affinity=round(rng.uniform(-0.25, 0.55), 2),
                        trust=round(rng.uniform(0.20, 0.55), 2),
                        loyalty=round(rng.uniform(0.15, 0.50), 2),
                        obligation=round(rng.uniform(0.05, 0.40), 2),
                        tags=[rng.choice(list(RelationshipTag))],
                        is_revealed_to_player=False,
                    )
                )
                existing_pairs.add(pair)

    relationship_graph = RelationshipGraph(edges=edges)

    config = SimulationConfig(
        case_id=f"case_{tpl.template_id}_seed_{seed}",
        seed=seed,
        start_min=1080,
        end_min=1440,
        tick_size_min=10,
        victim_id=victim_id,
        crime_location_id=crime_location_id,
        murder_window=TimeInterval(start_min=1260, end_min=1280),
        witness_noise_rate=0.15,
        record_drop_rate=0.20,
        guilty_lie_rate=0.90,
        innocent_lie_rate=0.25,
    )

    return SampledCaseSetup(
        setting=tpl,
        characters=characters,
        relationship_graph=relationship_graph,
        config=config,
    )


def generate_valid_case(
    template: SettingTemplate,
    base_seed: int = 42,
    num_suspects: int = 4,
    max_attempts: int = 20,
) -> tuple[SampledCaseSetup, SimulatedCaseBundle, CaseValidationReport]:
    """
    Samples a case setup starting from `base_seed` (re-trying incremental seeds up to
    `max_attempts` if needed) and verifies `CaseSolvabilityValidator.validate_case` passes.
    """
    last_setup: Optional[SampledCaseSetup] = None
    last_bundle: Optional[SimulatedCaseBundle] = None
    last_report: Optional[CaseValidationReport] = None

    for offset in range(max_attempts):
        candidate_seed = base_seed + offset
        setup = sample_case_setup_from_template(
            template=template,
            seed=candidate_seed,
            num_suspects=num_suspects,
            ood_mode=False,
        )
        bundle = setup.simulate()
        report = CaseSolvabilityValidator.validate_case(
            bundle=bundle,
            setting=template,
            allow_hard_cases=False,
        )
        last_setup, last_bundle, last_report = setup, bundle, report
        if report.is_valid:
            return setup, bundle, report

    assert last_setup is not None and last_bundle is not None and last_report is not None
    return last_setup, last_bundle, last_report

