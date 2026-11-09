# backend/app/engine/reveal_sampler.py
import math
import random

from pydantic import BaseModel, Field, field_validator

from app.domain.setting import SettingTemplate
from app.domain.simulation import SimulatedCaseBundle
from app.domain.tiers import T0Public, T1Session
from app.domain.world import Claim, Fact, TimeInterval

VALID_SNAPSHOT_SPLITS = {
    "train",
    "val",
    "test_in_dist",
    "test_held_out_template",
    "test_ood_shifted",
}


class EvidenceStateSnapshot(BaseModel):
    """
    PRD Section 8.3:
    Partial T1 investigation state captured at a specific reveal stage and ordering.
    Used for offline training and stage-wise evaluation of the SuspectRanker (M2)
    and calibrated abstention gate.
    """
    snapshot_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    template_id: str = Field(..., min_length=1)
    split: str = Field(
        ...,
        description="One of 'train', 'val', 'test_in_dist', 'test_held_out_template', 'test_ood_shifted'",
    )
    cv_fold: int | None = Field(
        default=None,
        description="Grouped CV fold (group = template) for train-split snapshots; None elsewhere",
    )
    difficulty: str | None = Field(default=None, description="Validator label: EASY / MEDIUM / HARD")
    setting: SettingTemplate | None = Field(
        default=None,
        description="This case's map (public T0 data), so features can be recomputed from the snapshot alone",
    )
    order_idx: int = Field(..., ge=0)
    stage_idx: int = Field(..., ge=0)
    reveal_fraction: float = Field(..., gt=0.0, le=1.0)
    t0_public: T0Public
    t1_partial: T1Session
    crime_location_id: str = Field(..., min_length=1)
    murder_window: TimeInterval
    is_under_determined_hard_case: bool = Field(default=False)
    interview_turns: int = Field(default=0, ge=0, description="Questions/record requests asked so far (0 = no interview)")
    culprit_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Stored ONLY on the offline training snapshot metadata for label assignment "
            "(y = 1 if suspect_id == culprit_id else 0); never passed into feature calculation functions."
        ),
    )

    @field_validator("split")
    @classmethod
    def validate_split(cls, value: str) -> str:
        if value not in VALID_SNAPSHOT_SPLITS:
            raise ValueError(
                f"Invalid snapshot split '{value}'. Expected one of {sorted(VALID_SNAPSHOT_SPLITS)}."
            )
        return value


class EvidenceRevealSampler:
    """
    PRD Section 8.3:
    Deterministic multi-stage evidence-reveal slicer that takes a validated
    `SimulatedCaseBundle` and produces partial `T1Session` snapshots across
    multiple investigation stages and reveal orderings.
    """

    @staticmethod
    def _select_baseline_and_remaining_facts(
        facts: list[Fact],
        crime_location_id: str,
    ) -> tuple[list[Fact], list[Fact]]:
        """
        Identifies at least 1 initial baseline briefing fact (preferring an initial
        crime-location discovery or access/timeline record) so stage 0 is never empty,
        and returns `(baseline_facts, remaining_facts)`.
        """
        if not facts:
            return [], []

        baseline_idx = 0
        for idx, fact in enumerate(facts):
            if fact.location_id == crime_location_id:
                baseline_idx = idx
                break

        baseline_facts = [facts[baseline_idx].model_copy(deep=True)]
        remaining_facts = [
            f.model_copy(deep=True)
            for idx, f in enumerate(facts)
            if idx != baseline_idx
        ]
        return baseline_facts, remaining_facts

    @classmethod
    def sample_reveal_snapshots(
        cls,
        bundle: SimulatedCaseBundle,
        template: SettingTemplate,
        split: str,
        num_orderings: int = 2,
        stage_fractions: tuple[float, ...] = (0.35, 0.65, 1.0),
        is_under_determined_hard_case: bool = False,
    ) -> list[EvidenceStateSnapshot]:
        """
        Deterministically slices `bundle.t1_session` across `num_orderings` distinct
        reveal sequences and `stage_fractions` investigation stages.

        - Uses an isolated `random.Random(bundle.config.seed + 1000)` instance.
        - Preserves baseline briefing fact(s) at the start of every ordering so
          stage 0 is never empty, and permutes remaining facts and claims.
        - Monotonically reveals facts and claims as `reveal_fraction` increases.
        - Emits `reveal_fraction == 1.0` once (`order_idx == 0`) since all orderings
          converge at 100% revealed, matching `bundle.t1_session`.
        - Enforces PRD Section 8.3 rule: all snapshots from `bundle.config.case_id`
          carry the exact same `split` value.
        """
        if split not in VALID_SNAPSHOT_SPLITS:
            raise ValueError(
                f"Invalid split '{split}'. Expected one of {sorted(VALID_SNAPSHOT_SPLITS)}."
            )
        if num_orderings < 1:
            raise ValueError(f"num_orderings must be >= 1 (got {num_orderings}).")
        if not stage_fractions:
            raise ValueError("stage_fractions must be non-empty.")
        for frac in stage_fractions:
            if frac <= 0.0 or frac > 1.0:
                raise ValueError(
                    f"Each reveal_fraction must be in (0.0, 1.0], got {frac}."
                )

        rng = random.Random(bundle.config.seed + 1000)

        case_id = bundle.config.case_id
        template_id = template.template_id
        crime_location_id = (
            bundle.t0_public.crime_location_id or bundle.config.crime_location_id
        )
        murder_window = (
            bundle.t0_public.crime_window or bundle.config.murder_window
        )
        culprit_id = bundle.t3_canonical.culprit_id

        all_facts = [f.model_copy(deep=True) for f in bundle.t1_session.discovered_facts]
        all_claims = [c.model_copy(deep=True) for c in bundle.t1_session.recorded_claims]

        baseline_facts, remaining_facts = cls._select_baseline_and_remaining_facts(
            all_facts, crime_location_id
        )

        # Build deterministic per-ordering sequences of facts and claims
        orderings_facts: list[list[Fact]] = []
        orderings_claims: list[list[Claim]] = []
        for _ in range(num_orderings):
            perm_remaining_facts = [f.model_copy(deep=True) for f in remaining_facts]
            rng.shuffle(perm_remaining_facts)
            orderings_facts.append(
                [f.model_copy(deep=True) for f in baseline_facts] + perm_remaining_facts
            )

            perm_claims = [c.model_copy(deep=True) for c in all_claims]
            rng.shuffle(perm_claims)
            orderings_claims.append(perm_claims)

        snapshots: list[EvidenceStateSnapshot] = []
        emitted_full_stage = False

        for order_idx in range(num_orderings):
            ordered_facts = orderings_facts[order_idx]
            ordered_claims = orderings_claims[order_idx]
            total_facts = len(ordered_facts)
            total_claims = len(ordered_claims)

            for stage_idx, reveal_fraction in enumerate(stage_fractions):
                is_full_reveal = math.isclose(reveal_fraction, 1.0, rel_tol=1e-9, abs_tol=1e-9)
                if is_full_reveal:
                    if emitted_full_stage:
                        continue
                    emitted_full_stage = True
                    t1_partial = bundle.t1_session.model_copy(deep=True)
                    effective_order_idx = 0
                else:
                    effective_order_idx = order_idx
                    if total_facts > 0:
                        k_facts = min(
                            total_facts,
                            max(len(baseline_facts), math.ceil(total_facts * reveal_fraction)),
                        )
                    else:
                        k_facts = 0

                    if total_claims > 0:
                        k_claims = min(
                            total_claims,
                            max(1, math.ceil(total_claims * reveal_fraction)),
                        )
                    else:
                        k_claims = 0

                    staged_facts = [f.model_copy(deep=True) for f in ordered_facts[:k_facts]]
                    staged_claims = [c.model_copy(deep=True) for c in ordered_claims[:k_claims]]

                    # A relationship is visible only once the fact that revealed it is staged.
                    staged_fact_ids = {f.fact_id for f in staged_facts}
                    staged_edges = [
                        edge.model_copy(deep=True)
                        for edge in bundle.t1_session.revealed_edges
                        if edge.evidence_fact_id in staged_fact_ids
                    ]

                    t1_partial = T1Session(
                        session_id=bundle.t1_session.session_id,
                        case_id=case_id,
                        current_turn=bundle.t1_session.current_turn,
                        discovered_facts=staged_facts,
                        recorded_claims=staged_claims,
                        contradiction_flags=[],
                        revealed_edges=staged_edges,
                    )

                snapshot_id = f"{case_id}_ord{effective_order_idx}_stg{stage_idx}"
                snapshots.append(
                    EvidenceStateSnapshot(
                        snapshot_id=snapshot_id,
                        case_id=case_id,
                        template_id=template_id,
                        split=split,
                        order_idx=effective_order_idx,
                        stage_idx=stage_idx,
                        reveal_fraction=round(float(reveal_fraction), 4),
                        t0_public=bundle.t0_public.model_copy(deep=True),
                        t1_partial=t1_partial,
                        crime_location_id=crime_location_id,
                        murder_window=murder_window.model_copy(deep=True),
                        is_under_determined_hard_case=is_under_determined_hard_case,
                        culprit_id=culprit_id,
                    )
                )

        return snapshots


def sample_reveal_snapshots(
    bundle: SimulatedCaseBundle,
    template: SettingTemplate,
    split: str,
    num_orderings: int = 2,
    stage_fractions: tuple[float, ...] = (0.35, 0.65, 1.0),
    is_under_determined_hard_case: bool = False,
) -> list[EvidenceStateSnapshot]:
    """Module-level wrapper for EvidenceRevealSampler.sample_reveal_snapshots()."""
    return EvidenceRevealSampler.sample_reveal_snapshots(
        bundle=bundle,
        template=template,
        split=split,
        num_orderings=num_orderings,
        stage_fractions=stage_fractions,
        is_under_determined_hard_case=is_under_determined_hard_case,
    )

