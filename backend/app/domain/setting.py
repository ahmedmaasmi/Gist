# backend/app/domain/setting.py
from typing import Any

from pydantic import BaseModel, Field, model_validator

VALID_SPLIT_GROUPS = {"train", "val", "test_held_out_template"}


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
        ...,
        description="Symmetric or directed minimum travel time in minutes between location_A and location_B",
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
        default="train",
        description="Default split assignment: 'train', 'val', or 'test_held_out_template' per PRD Section 8.4",
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
