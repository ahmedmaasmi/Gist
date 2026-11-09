# backend/app/domain/setting.py
import math
import random
from typing import Any

from pydantic import BaseModel, Field, model_validator

# PRD 8.4: templates are either used for development (their cases are split train/val/test by case)
# or held out entirely as the template-held-out test set.
VALID_SPLIT_GROUPS = {"dev", "test_held_out_template"}


def shortest_paths(nodes: list[str], weights: dict[tuple[str, str], int]) -> dict[str, dict[str, int]]:
    """
    Floyd-Warshall over symmetric edge weights. The result is a proper map metric: symmetric,
    zero on the diagonal, and no detour is ever shorter than the direct route (triangle inequality).
    Unreachable pairs are left out, so the completeness check below reports them.
    """
    inf = math.inf
    dist = {a: {b: (0 if a == b else inf) for b in nodes} for a in nodes}
    for (a, b), w in weights.items():
        dist[a][b] = min(dist[a][b], w)
        dist[b][a] = min(dist[b][a], w)
    for k in nodes:
        for i in nodes:
            for j in nodes:
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]
    return {a: {b: int(d) for b, d in row.items() if d != inf} for a, row in dist.items()}


class Location(BaseModel):
    """
    PRD Section 6.4.B & 7B.2: Spatial node in a case setting template.
    """
    location_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    is_restricted: bool = Field(
        default=False,
        description="True if entry requires specific access/keycard",
    )
    x: float | None = Field(default=None, description="Floor-plan position, in walking minutes")
    y: float | None = Field(default=None, description="Floor-plan position, in walking minutes")


class SettingTemplate(BaseModel):
    """
    PRD Section 6.4.B, 7B.2, 7B.4 (CL-06), 8.1 & 8.4:
    Spatial geometry, travel-time rules, and procedural sampling metadata of a case setting
    (e.g., Blackwood Manor or Night Express to Ashford).
    """
    template_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    locations: list[Location] = Field(
        ...,
        min_length=3,
        max_length=8,
        description="CL-06: At least 3 and at most 8 locations per setting template",
    )
    travel_matrix: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description=(
            "Minimum travel time in minutes between location_A and location_B. Built from `connections` "
            "and room positions when omitted."
        ),
    )
    connections: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Doorways/corridors between rooms; walking time = straight-line distance between positions",
    )
    default_crime_location_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Candidate locations where a murder can take place, typically restricted or secluded rooms",
    )
    archetype_occupations: list[str] = Field(
        default_factory=list,
        description="Pool of setting-appropriate occupations for procedural character generation",
    )
    split_group: str = Field(
        default="dev",
        description="'dev' (cases split train/val/test by case) or 'test_held_out_template' (PRD 8.4)",
    )

    @model_validator(mode="before")
    @classmethod
    def populate_default_crime_locations_if_omitted(cls, data: Any) -> Any:
        """
        If default_crime_location_ids is omitted by caller, default to restricted locations
        (or first location if none are restricted) so existing callers remain ergonomic while
        still enforcing min_length=1 when explicitly provided.
        """
        if isinstance(data, dict) and "default_crime_location_ids" not in data:
            raw_locs = data.get("locations")
            if isinstance(raw_locs, list) and len(raw_locs) > 0:
                restricted_ids: list[str] = []
                all_ids: list[str] = []
                for item in raw_locs:
                    if isinstance(item, Location):
                        all_ids.append(item.location_id)
                        if item.is_restricted:
                            restricted_ids.append(item.location_id)
                    elif isinstance(item, dict) and "location_id" in item:
                        all_ids.append(str(item["location_id"]))
                        if item.get("is_restricted"):
                            restricted_ids.append(str(item["location_id"]))
                inferred = restricted_ids if restricted_ids else all_ids[:1]
                if inferred:
                    data = {**data, "default_crime_location_ids": inferred}
        return data

    @model_validator(mode="before")
    @classmethod
    def build_travel_matrix_from_layout(cls, data: Any) -> Any:
        """
        Maps are authored as a floor plan: rooms with (x, y) positions plus the corridors between them.
        Each corridor takes max(1, round(distance)) minutes; travel time is the shortest walk.
        """
        if isinstance(data, dict) and not data.get("travel_matrix") and data.get("connections"):
            locs = [
                loc if isinstance(loc, dict) else loc.model_dump()
                for loc in data.get("locations", [])
            ]
            pos = {loc["location_id"]: (loc.get("x"), loc.get("y")) for loc in locs}
            weights: dict[tuple[str, str], int] = {}
            for a, b in data["connections"]:
                if a not in pos or b not in pos or None in pos[a] or None in pos[b]:
                    raise ValueError(f"Connection ({a}, {b}) needs two known rooms with x/y positions.")
                (xa, ya), (xb, yb) = pos[a], pos[b]
                weights[(a, b)] = max(1, round(math.hypot(xa - xb, ya - yb)))
            data = {**data, "travel_matrix": shortest_paths(list(pos), weights)}
        return data

    def with_travel_variation(self, rng: random.Random, low: float, high: float) -> "SettingTemplate":
        """
        A per-case variant of this map: every direct travel time is scaled by a factor in [low, high]
        (corridors are busier or quieter that evening), then shortest paths are recomputed so the
        result is still a consistent map.
        """
        ids = sorted(loc.location_id for loc in self.locations)
        weights = {
            (a, b): max(1, round(self.travel_matrix[a][b] * rng.uniform(low, high)))
            for i, a in enumerate(ids)
            for b in ids[i + 1 :]
        }
        return self.model_copy(update={"travel_matrix": shortest_paths(ids, weights)}, deep=True)

    @model_validator(mode="after")
    def validate_setting_template(self) -> "SettingTemplate":
        valid_ids = {loc.location_id for loc in self.locations}
        if len(valid_ids) != len(self.locations):
            raise ValueError("SettingTemplate locations must have unique location_id values.")

        if self.split_group not in VALID_SPLIT_GROUPS:
            raise ValueError(
                f"Invalid split_group '{self.split_group}'. "
                f"Expected one of {sorted(VALID_SPLIT_GROUPS)}."
            )

        for crime_loc_id in self.default_crime_location_ids:
            if crime_loc_id not in valid_ids:
                raise ValueError(
                    f"default_crime_location_ids contains unknown location_id '{crime_loc_id}'. "
                    f"Valid location_ids: {sorted(valid_ids)}"
                )

        # First verify no unknown origins/destinations or negative times exist
        for origin_id, dest_map in self.travel_matrix.items():
            if origin_id not in valid_ids:
                raise ValueError(
                    f"travel_matrix contains unknown origin location_id '{origin_id}'. "
                    f"Valid location_ids: {sorted(valid_ids)}"
                )
            for dest_id, minutes in dest_map.items():
                if dest_id not in valid_ids:
                    raise ValueError(
                        f"travel_matrix['{origin_id}'] contains unknown destination "
                        f"location_id '{dest_id}'. Valid location_ids: {sorted(valid_ids)}"
                    )
                if minutes < 0:
                    raise ValueError(
                        f"travel_matrix['{origin_id}']['{dest_id}'] cannot have negative "
                        f"travel time ({minutes})."
                    )

        # Verify travel_matrix is complete across all location pairs
        for origin_id in sorted(valid_ids):
            if origin_id not in self.travel_matrix:
                raise ValueError(
                    f"travel_matrix is incomplete: missing origin location_id '{origin_id}'."
                )
            dest_map = self.travel_matrix[origin_id]
            dest_map.setdefault(origin_id, 0)
            for dest_id in sorted(valid_ids):
                if dest_id not in dest_map:
                    raise ValueError(
                        f"travel_matrix['{origin_id}'] is incomplete: missing travel time "
                        f"to destination location_id '{dest_id}'."
                    )

        return self

    def get_travel_time(self, loc_a: str, loc_b: str) -> int:
        """
        Returns minimum travel time in minutes from loc_a to loc_b.
        Returns 0 if loc_a == loc_b.
        """
        if loc_a == loc_b:
            return 0
        return self.travel_matrix.get(loc_a, {}).get(loc_b, 0)
