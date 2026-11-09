# backend/app/engine/templates.py
import json
import random
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel

from app.domain.character import (
    TRAIT_TRAINING_RANGE,
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

NAMES_PATH = Path(__file__).resolve().parents[3] / "data" / "names.json"

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
    _cache: dict[str, SettingTemplate] | None = None

    @classmethod
    def load_all_templates(
        cls,
        templates_dir: Path | str | None = None,
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
        templates_dir: Path | str | None = None,
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
        templates_dir: Path | str | None = None,
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
    templates_dir: Path | str | None = None,
    force_reload: bool = False,
) -> dict[str, SettingTemplate]:
    """Module-level wrapper for TemplateRegistry.load_all_templates()."""
    return TemplateRegistry.load_all_templates(
        templates_dir=templates_dir,
        force_reload=force_reload,
    )


def get_template(
    template_id: str,
    templates_dir: Path | str | None = None,
) -> SettingTemplate:
    """Module-level wrapper for TemplateRegistry.get_template()."""
    return TemplateRegistry.get_template(
        template_id=template_id,
        templates_dir=templates_dir,
    )


def get_templates_by_split(
    split_group: str,
    templates_dir: Path | str | None = None,
) -> list[SettingTemplate]:
    """Module-level wrapper for TemplateRegistry.get_templates_by_split()."""
    return TemplateRegistry.get_templates_by_split(
        split_group=split_group,
        templates_dir=templates_dir,
    )


TRAIT_NAMES = ("temper", "greed", "loyalty", "honesty", "composure", "secrecy")
MOTIVE_GOAL_TYPES = (GoalType.REVENGE, GoalType.INHERITANCE, GoalType.MONEY, GoalType.HIDE_SECRET)
VICTIM_SECRET_TOPICS = (
    "fraudulent accounts",
    "a forged signature on a contract",
    "an affair",
    "embezzled funds",
    "a hidden gambling debt",
)
PRIVATE_SECRET_TOPICS = (
    "an unrelated regulatory infraction",
    "a private meeting with a rival firm",
    "unauthorized side business",
    "a past criminal conviction",
    "a family scandal",
)

# Sampling probabilities for the role-free cast. Documented here because they shape how hard
# the generated cases are (PRD 8.2: the generator is documented with its parameters).
P_MOTIVE_GOAL = 0.5        # suspect has a grievance against the victim
P_PROTECT_GOAL = 0.3       # suspect wants to protect another suspect
P_VICTIM_SECRET = 0.5      # suspect has a secret the victim could expose (potential motive)
P_PRIVATE_SECRET = 0.6     # suspect has an unrelated secret (potential red herring)
P_EDGE = 0.6               # a directed relationship edge exists between two characters
P_SCENE_SLOT = 0.15        # a schedule slot is planned at the crime location
CULPRIT_TEMPERATURE = 0.5  # softmax temperature for culprit selection (see SimulationConfig)

# Per-case variables (PRD 8.2: noise, deception; the generator is documented with its parameters).
# Every case draws one value from each range; the drawn values are stored in its SimulationConfig and
# the ranges in the dataset manifest. Anything outside these ranges is out-of-distribution by definition.
CASE_VARIABLE_RANGES: dict[str, tuple[float, float]] = {
    "num_suspects": (3, 6),
    "murder_window_start_min": (1200, 1380),  # 20:00 to 23:00, on 10-minute ticks
    "murder_window_length_min": (20, 40),     # on 10-minute ticks
    "travel_time_factor": (0.8, 1.2),         # per-corridor variation of the map (with_travel_variation)
    "witness_noise_rate": (0.05, 0.30),
    "record_drop_rate": (0.10, 0.35),
    "forensic_trace_rate": (0.50, 0.90),
    "guilty_lie_rate": (0.60, 1.00),
    "innocent_lie_rate": (0.10, 0.40),
}


def load_name_pool(path: Path = NAMES_PATH) -> list[str]:
    """Famous historical and public-domain fictional names (data/names.json). Flavour only (PRD 7A.1)."""
    return [entry["name"] for entry in json.loads(path.read_text(encoding="utf-8"))["names"]]


def _draw(rng: random.Random, variable: str) -> float:
    low, high = CASE_VARIABLE_RANGES[variable]
    return round(rng.uniform(low, high), 3)


def _draw_tick(rng: random.Random, variable: str, tick_size_min: int = 10) -> int:
    low, high = CASE_VARIABLE_RANGES[variable]
    return rng.randrange(int(low), int(high) + 1, tick_size_min)


def _sample_traits(rng: random.Random) -> CharacterTraits:
    """Every trait uniform over the full editor range (PRD 8.2 implementation note, CH-04)."""
    low, high = TRAIT_TRAINING_RANGE
    return CharacterTraits(**{name: round(rng.uniform(low, high), 2) for name in TRAIT_NAMES})


def _sample_schedule(
    rng: random.Random,
    setting: SettingTemplate,
    locations: list[str],
    crime_location_id: str,
    start_min: int = 1080,
    end_min: int = 1440,
    tick_size_min: int = 10,
) -> list[ScheduleSlot]:
    """
    3 to 5 consecutive slots at random 10-minute boundaries; occasionally at the crime scene.
    Each slot's location is reachable from the previous one within one tick, so nobody "teleports"
    across the map between ticks (which would create travel-time contradictions nobody caused).
    """
    n_slots = rng.randint(3, 5)
    cuts = sorted(rng.sample(range(start_min + 30, end_min - 30, 10), n_slots - 1))
    bounds = [start_min, *cuts, end_min]
    slots: list[ScheduleSlot] = []
    prev: str | None = None
    for a, b in zip(bounds, bounds[1:], strict=False):
        def reachable(loc: str, prev: str | None = prev) -> bool:
            return prev is None or setting.get_travel_time(prev, loc) <= tick_size_min

        options = [loc for loc in locations if reachable(loc)] or [prev or locations[0]]
        if reachable(crime_location_id) and rng.random() < P_SCENE_SLOT:
            loc = crime_location_id
        else:
            loc = rng.choice(options)
        slots.append(ScheduleSlot(time_interval=TimeInterval(start_min=a, end_min=b), planned_location_id=loc))
        prev = loc
    return slots


def sample_case_setup_from_template(
    template: SettingTemplate,
    seed: int,
    num_suspects: int | None = None,
) -> SampledCaseSetup:
    """
    PRD Section 7B.2, 7B.4 (CL-06), 8.2, and CH-03/CH-04:
    Procedurally samples a complete case setup (characters, schedules, secrets, goals,
    asymmetric RelationshipGraph, and SimulationConfig) from a `SettingTemplate`
    using an isolated `random.Random(seed)` instance.

    Every variable in CASE_VARIABLE_RANGES is drawn per case (num_suspects only if not given).
    """
    rng = random.Random(seed)
    if num_suspects is None:
        low, high = CASE_VARIABLE_RANGES["num_suspects"]
        num_suspects = rng.randint(int(low), int(high))
    if num_suspects < 3 or num_suspects > 6:
        raise ValueError(
            f"CL-06 Violation: num_suspects must be between 3 and 6 (got {num_suspects})."
        )

    # This evening's version of the map: corridor times vary a little from case to case.
    tpl = template.with_travel_variation(rng, *CASE_VARIABLE_RANGES["travel_time_factor"])
    window_start = _draw_tick(rng, "murder_window_start_min")
    murder_window = TimeInterval(
        start_min=window_start,
        end_min=window_start + _draw_tick(rng, "murder_window_length_min"),
    )

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

    # 2. Famous names (historical and public-domain fictional), drawn independently of everything
    #    else, so no name is more likely to be guilty than another. Occupations fit the setting.
    names = rng.sample(load_name_pool(), num_suspects + 1)

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
    victim_name = names[0]
    victim_occupation = occupations[0]

    victim_traits = _sample_traits(rng)

    # The victim goes to the crime room 20 minutes before the window and stays there.
    victim_schedule = [
        ScheduleSlot(
            time_interval=TimeInterval(start_min=1080, end_min=murder_window.start_min - 20),
            planned_location_id=social_hub_loc,
        ),
        ScheduleSlot(
            time_interval=TimeInterval(start_min=murder_window.start_min - 20, end_min=1440),
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

    # Role-free cast (PRD 8.2): every suspect is drawn from the same distribution, so there is
    # no scripted "primary". Motive, opportunity and temperament vary independently; the
    # simulator later picks the culprit from them with noise (culprit_temperature).
    non_crime_locs = [
        loc.location_id for loc in tpl.locations if loc.location_id != crime_location_id
    ]
    suspect_ids = [f"suspect_{idx + 1:02d}" for idx in range(num_suspects)]

    suspect_chars: list[Character] = []
    for idx, suspect_id in enumerate(suspect_ids):
        full_name = names[idx + 1]
        occ = occupations[(idx + 1) % len(occupations)]
        voice = VOICE_NOTES_POOL[(idx + 1) % len(VOICE_NOTES_POOL)]

        goals: list[CharacterGoal] = []
        if rng.random() < P_MOTIVE_GOAL:
            goal_type = rng.choice(MOTIVE_GOAL_TYPES)
            goals.append(
                CharacterGoal(
                    goal_type=goal_type,
                    target_character_id=victim_id,
                    description=(
                        f"{full_name} has a {goal_type.value.lower()} grievance against {victim_name}."
                    ),
                )
            )
        if rng.random() < P_PROTECT_GOAL:
            protected = rng.choice([s for s in suspect_ids if s != suspect_id])
            goals.append(
                CharacterGoal(
                    goal_type=GoalType.PROTECT_SOMEONE,
                    target_character_id=protected,
                    description=f"{full_name} wants to shield {protected} from scrutiny.",
                )
            )

        secrets: list[CharacterSecret] = []
        if rng.random() < P_VICTIM_SECRET:
            secrets.append(
                CharacterSecret(
                    secret_id=f"sec_{suspect_id}_{len(secrets) + 1}",
                    description=(
                        f"{full_name} was about to be exposed by {victim_name} over "
                        f"{rng.choice(VICTIM_SECRET_TOPICS)}."
                    ),
                    severity=round(rng.uniform(0.30, 0.95), 2),
                    is_crime_linked=False,  # set by the simulator if this suspect becomes the culprit
                    involves_character_id=victim_id,
                )
            )
        if rng.random() < P_PRIVATE_SECRET:
            secrets.append(
                CharacterSecret(
                    secret_id=f"sec_{suspect_id}_{len(secrets) + 1}",
                    description=f"{full_name} is hiding {rng.choice(PRIVATE_SECRET_TOPICS)}.",
                    severity=round(rng.uniform(0.20, 0.80), 2),
                    is_crime_linked=False,
                )
            )

        suspect_chars.append(
            Character(
                character_id=suspect_id,
                name=full_name,
                occupation=occ,
                voice_notes=voice,
                traits=_sample_traits(rng),
                goals=goals,
                secrets=secrets,
                schedule=_sample_schedule(rng, tpl, non_crime_locs, crime_location_id),
            )
        )

    characters: list[Character] = [victim_char, *suspect_chars]

    # Random asymmetric relationship graph over all characters (PRD 7A.2).
    grievance_ids = {
        c.character_id
        for c in suspect_chars
        if any(g.target_character_id == victim_id for g in c.goals)
    }
    edges: list[RelationshipEdge] = []
    for char_a in characters:
        for char_b in characters:
            if char_a.character_id == char_b.character_id or rng.random() >= P_EDGE:
                continue
            # A grievance against the victim makes hostility toward them more likely, not certain.
            max_affinity = (
                0.2
                if char_a.character_id in grievance_ids and char_b.character_id == victim_id
                else 1.0
            )
            edges.append(
                RelationshipEdge(
                    source_id=char_a.character_id,
                    target_id=char_b.character_id,
                    affinity=round(rng.uniform(-1.0, max_affinity), 2),
                    trust=round(rng.uniform(0.0, 1.0), 2),
                    loyalty=round(rng.uniform(0.0, 1.0), 2),
                    # Squared so strong debts/favours are rarer than weak ones.
                    obligation=round(rng.uniform(0.0, 1.0) ** 2, 2),
                    tags=[rng.choice(list(RelationshipTag))],
                    is_revealed_to_player=False,
                )
            )

    relationship_graph = RelationshipGraph(edges=edges)

    config = SimulationConfig(
        case_id=f"case_{tpl.template_id}_seed_{seed}",
        seed=seed,
        start_min=1080,
        end_min=1440,
        tick_size_min=10,
        victim_id=victim_id,
        crime_location_id=crime_location_id,
        murder_window=murder_window,
        witness_noise_rate=_draw(rng, "witness_noise_rate"),
        record_drop_rate=_draw(rng, "record_drop_rate"),
        forensic_trace_rate=_draw(rng, "forensic_trace_rate"),
        guilty_lie_rate=_draw(rng, "guilty_lie_rate"),
        innocent_lie_rate=_draw(rng, "innocent_lie_rate"),
        culprit_temperature=CULPRIT_TEMPERATURE,
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
    allow_hard_cases: bool = True,
) -> tuple[SampledCaseSetup, SimulatedCaseBundle, CaseValidationReport]:
    """
    Samples a case setup starting from `base_seed` (re-trying incremental seeds up to
    `max_attempts` if needed) and verifies `CaseSolvabilityValidator.validate_case` passes.

    By default only checks 1-3 (culprit possible, not trivial, red herring exists) gate the case;
    check 4 (culprit has the top hand-weighted score) only sets the difficulty label. Gating on
    check 4 would keep only cases a simple rule solves and bias the lie rate (D-010).
    """
    last_setup: SampledCaseSetup | None = None
    last_bundle: SimulatedCaseBundle | None = None
    last_report: CaseValidationReport | None = None

    for offset in range(max_attempts):
        candidate_seed = base_seed + offset
        setup = sample_case_setup_from_template(
            template=template,
            seed=candidate_seed,
            num_suspects=num_suspects,
        )
        bundle = setup.simulate()
        report = CaseSolvabilityValidator.validate_case(
            bundle=bundle,
            setting=template,
            allow_hard_cases=allow_hard_cases,
        )
        last_setup, last_bundle, last_report = setup, bundle, report
        if report.is_valid:
            return setup, bundle, report

    assert last_setup is not None and last_bundle is not None and last_report is not None
    return last_setup, last_bundle, last_report

