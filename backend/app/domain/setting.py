# backend/app/domain/setting.py
from pydantic import BaseModel, Field, model_validator


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
    PRD Section 6.4.B & 7B.2: Spatial geometry and travel-time rules of a case setting
    (e.g., Blackwood Manor or Last Train to Ashford).
    """
    template_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    locations: list[Location] = Field(default_factory=list)
    travel_matrix: dict[str, dict[str, int]] = Field(
        ...,
        description="Symmetric or directed minimum travel time in minutes between location_A and location_B",
    )

    @model_validator(mode="after")
    def validate_travel_matrix_locations(self) -> "SettingTemplate":
        valid_ids = {loc.location_id for loc in self.locations}
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
        return self

    def get_travel_time(self, loc_a: str, loc_b: str) -> int:
        """
        Returns minimum travel time in minutes from loc_a to loc_b.
        Returns 0 if loc_a == loc_b.
        """
        if loc_a == loc_b:
            return 0
        return self.travel_matrix.get(loc_a, {}).get(loc_b, 0)

