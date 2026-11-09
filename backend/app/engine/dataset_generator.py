# backend/app/engine/dataset_generator.py
import json
import random
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from app.domain.enums import EvidenceCategory
from app.domain.setting import SettingTemplate
from app.domain.simulation import SimulatedCaseBundle
from app.engine.reveal_sampler import EvidenceRevealSampler, EvidenceStateSnapshot
from app.engine.solver import CaseSolvabilityValidator, CaseValidationReport
from app.engine.templates import TemplateRegistry, sample_case_setup_from_template


class DatasetManifest(BaseModel):
    """
    PRD Section 8.1 & 10.3:
    Reproducibility and dataset-versioning manifest explicitly reporting both the
    number of structural setting templates (`num_templates_total`) and total generated
    case instances (`num_cases_total`), along with split distributions and parameters.
    """
    dataset_version: str = Field(default="v0.1.0", min_length=1)
    master_seed: int
    num_templates_total: int = Field(..., ge=1)
    num_cases_total: int = Field(..., ge=1)
    cases_by_split: dict[str, int] = Field(default_factory=dict)
    snapshots_by_split: dict[str, int] = Field(default_factory=dict)
    hard_cases_count: int = Field(
        default=0,
        ge=0,
        description="Under-determined cases generated for E4 abstention evaluation",
    )
    generator_params: dict[str, float | int] = Field(default_factory=dict)


class DatasetGenerator:
    """
    PRD Section 8.1–8.4 & Section 10.3:
    Generates, validates, slices, and persists reproducible synthetic case datasets
    across the 8 setting templates with strict case-level and template-held-out
    split isolation.
    """

    DEFAULT_STAGE_FRACTIONS: tuple[float, ...] = (0.35, 0.65, 1.0)

    @staticmethod
    def _make_under_determined_variant(
        bundle: SimulatedCaseBundle,
    ) -> SimulatedCaseBundle:
        """
        PRD Section 8.2 (E4 Abstention / Hard Case slice):
        Produces an under-determined variant of a valid simulated case by withholding
        culprit-specific crime-scene movement/forensic traces and secondary crime-linked
        secret records from `t1_session.discovered_facts` (while preserving the culprit's
        primary motive fact so the culprit remains plausible and tied with the innocent
        red-herring suspect on discoverable T1 evidence).
        """
        variant = bundle.model_copy(deep=True)
        culprit_id = variant.t3_canonical.culprit_id
        crime_loc = variant.t0_public.crime_location_id or variant.config.crime_location_id

        kept_facts = []
        kept_culprit_motive = False
        for fact in variant.t1_session.discovered_facts:
            if fact.subject_id == culprit_id:
                # Drop crime-location physical/access/timeline traces for the culprit
                if fact.location_id == crime_loc and fact.category in (
                    EvidenceCategory.ACCESS,
                    EvidenceCategory.TIMELINE,
                    EvidenceCategory.FORENSIC,
                ):
                    continue
                # Keep at most 1 motive fact for the culprit so culprit ties with red herring
                if fact.category == EvidenceCategory.MOTIVE:
                    if kept_culprit_motive:
                        continue
                    kept_culprit_motive = True
            kept_facts.append(fact)

        variant.t1_session.discovered_facts = kept_facts
        return variant

    @classmethod
    def _generate_validated_case_for_slot(
        cls,
        template: SettingTemplate,
        case_id: str,
        base_seed: int,
        num_suspects: int,
        target_hard_case: bool,
        max_attempts: int = 25,
    ) -> tuple[SimulatedCaseBundle, CaseValidationReport]:
        """
        Generates a case for `(template, case_id)` starting from `base_seed`, re-rolling
        with incremented sub-seeds until `CaseSolvabilityValidator.validate_case` passes.
        """
        last_bundle: Optional[SimulatedCaseBundle] = None
        last_report: Optional[CaseValidationReport] = None

        for offset in range(max_attempts):
            sub_seed = base_seed + offset
            setup = sample_case_setup_from_template(
                template=template,
                seed=sub_seed,
                num_suspects=num_suspects,
                ood_mode=False,
            )
            setup.config.case_id = case_id
            bundle = setup.simulate()

            if target_hard_case:
                hard_bundle = cls._make_under_determined_variant(bundle)
                hard_report = CaseSolvabilityValidator.validate_case(
                    bundle=hard_bundle,
                    setting=template,
                    allow_hard_cases=True,
                )
                last_bundle, last_report = hard_bundle, hard_report
                if hard_report.is_valid and hard_report.is_under_determined_hard_case:
                    return hard_bundle, hard_report

            report = CaseSolvabilityValidator.validate_case(
                bundle=bundle,
                setting=template,
                allow_hard_cases=target_hard_case,
            )
            last_bundle, last_report = bundle, report
            if report.is_valid:
                return bundle, report

        assert last_bundle is not None and last_report is not None
        raise RuntimeError(
            f"Failed to generate a valid case for '{case_id}' (template='{template.template_id}') "
            f"after {max_attempts} attempts: {last_report.failure_reasons}"
        )

    @classmethod
    def generate_dataset(
        cls,
        total_cases: int = 240,
        master_seed: int = 2026,
        hard_case_ratio: float = 0.10,
        num_orderings: int = 2,
        stage_fractions: tuple[float, ...] = DEFAULT_STAGE_FRACTIONS,
        templates_dir: Optional[Path | str] = None,
    ) -> tuple[list[EvidenceStateSnapshot], DatasetManifest]:
        """
        PRD Section 8.1–8.4 & 10.3:
        Generates `total_cases` validated synthetic cases across the 8 templates,
        applies multi-stage evidence-reveal slicing (`EvidenceRevealSampler`),
        and returns `(snapshots, manifest)`.
        """
        if total_cases < 1:
            raise ValueError(f"total_cases must be >= 1 (got {total_cases}).")
        if not (0.0 <= hard_case_ratio <= 1.0):
            raise ValueError(
                f"hard_case_ratio must be in [0.0, 1.0] (got {hard_case_ratio})."
            )
        if num_orderings < 1:
            raise ValueError(f"num_orderings must be >= 1 (got {num_orderings}).")

        rng = random.Random(master_seed)
        templates_map = TemplateRegistry.load_all_templates(templates_dir=templates_dir)
        templates_sorted = [templates_map[k] for k in sorted(templates_map.keys())]
        num_templates = len(templates_sorted)

        # 1. Distribute total_cases evenly across the 8 templates
        base_per_tpl = total_cases // num_templates
        remainder = total_cases % num_templates
        counts_per_tpl: dict[str, int] = {}
        for idx, tpl in enumerate(templates_sorted):
            counts_per_tpl[tpl.template_id] = base_per_tpl + (1 if idx < remainder else 0)

        # 2. Build deterministic case plan: (global_idx, template, split)
        # Templates with split_group == "train" split their cases 85% "train" / 15% "test_in_dist"
        train_group_templates = [
            tpl for tpl in templates_sorted if tpl.split_group == "train"
        ]
        total_train_group_cases = sum(
            counts_per_tpl[tpl.template_id] for tpl in train_group_templates
        )
        if total_train_group_cases >= 2:
            target_in_dist_total = max(1, int(round(total_train_group_cases * 0.15)))
        else:
            target_in_dist_total = 0

        in_dist_per_train_tpl: dict[str, int] = {
            tpl.template_id: 0 for tpl in train_group_templates
        }
        if train_group_templates and target_in_dist_total > 0:
            for i in range(target_in_dist_total):
                tpl_id = train_group_templates[i % len(train_group_templates)].template_id
                if in_dist_per_train_tpl[tpl_id] < counts_per_tpl[tpl_id]:
                    in_dist_per_train_tpl[tpl_id] += 1

        case_specs: list[tuple[int, SettingTemplate, str]] = []
        global_idx = 0
        for tpl in templates_sorted:
            n_cases = counts_per_tpl[tpl.template_id]
            if tpl.split_group == "test_held_out_template":
                for _ in range(n_cases):
                    case_specs.append((global_idx, tpl, "test_held_out_template"))
                    global_idx += 1
            elif tpl.split_group == "val":
                for _ in range(n_cases):
                    case_specs.append((global_idx, tpl, "val"))
                    global_idx += 1
            else:
                # split_group == "train": first 85% -> "train", last 15% -> "test_in_dist"
                n_in_dist = in_dist_per_train_tpl.get(tpl.template_id, 0)
                n_train = n_cases - n_in_dist
                for i in range(n_cases):
                    assigned_split = "train" if i < n_train else "test_in_dist"
                    case_specs.append((global_idx, tpl, assigned_split))
                    global_idx += 1

        # 3. Select hard-case slots deterministically for the `hard_case_ratio` slice
        target_hard_cases = int(round(total_cases * hard_case_ratio))
        all_indices = list(range(total_cases))
        rng.shuffle(all_indices)
        hard_case_indices = set(all_indices[:target_hard_cases])

        # 4. Simulate, validate, and slice each case into EvidenceStateSnapshots
        all_snapshots: list[EvidenceStateSnapshot] = []
        cases_by_split: dict[str, int] = {
            "train": 0,
            "val": 0,
            "test_in_dist": 0,
            "test_held_out_template": 0,
        }
        snapshots_by_split: dict[str, int] = {
            "train": 0,
            "val": 0,
            "test_in_dist": 0,
            "test_held_out_template": 0,
        }
        hard_cases_count = 0

        suspect_counts_pool = (3, 4, 4, 5, 6)

        for case_idx, tpl, assigned_split in case_specs:
            case_base_seed = master_seed * 10000 + case_idx * 100
            num_suspects = suspect_counts_pool[case_idx % len(suspect_counts_pool)]
            is_hard_slot = case_idx in hard_case_indices
            case_id = f"case_{tpl.template_id}_{case_idx:04d}"

            bundle, report = cls._generate_validated_case_for_slot(
                template=tpl,
                case_id=case_id,
                base_seed=case_base_seed,
                num_suspects=num_suspects,
                target_hard_case=is_hard_slot,
            )

            if report.is_under_determined_hard_case:
                hard_cases_count += 1

            case_snapshots = EvidenceRevealSampler.sample_reveal_snapshots(
                bundle=bundle,
                template=tpl,
                split=assigned_split,
                num_orderings=num_orderings,
                stage_fractions=stage_fractions,
                is_under_determined_hard_case=report.is_under_determined_hard_case,
            )

            all_snapshots.extend(case_snapshots)
            cases_by_split[assigned_split] = cases_by_split.get(assigned_split, 0) + 1
            snapshots_by_split[assigned_split] = (
                snapshots_by_split.get(assigned_split, 0) + len(case_snapshots)
            )

        manifest = DatasetManifest(
            dataset_version="v0.1.0",
            master_seed=master_seed,
            num_templates_total=num_templates,
            num_cases_total=total_cases,
            cases_by_split=cases_by_split,
            snapshots_by_split=snapshots_by_split,
            hard_cases_count=hard_cases_count,
            generator_params={
                "total_cases": total_cases,
                "master_seed": master_seed,
                "hard_case_ratio": hard_case_ratio,
                "num_orderings": num_orderings,
                "num_stages": len(stage_fractions),
                "train_in_dist_ratio": 0.15,
            },
        )

        return all_snapshots, manifest

    @classmethod
    def save_dataset(
        cls,
        snapshots: list[EvidenceStateSnapshot],
        manifest: DatasetManifest,
        output_dir: Path | str,
    ) -> dict[str, Path]:
        """
        Persists `snapshots` as JSONL (`snapshots.jsonl`) and `manifest` as JSON (`manifest.json`)
        inside `output_dir`.
        """
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = target_dir / "manifest.json"
        snapshots_path = target_dir / "snapshots.jsonl"

        manifest_path.write_text(
            manifest.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            json.dumps(snap.model_dump(mode="json"), sort_keys=True)
            for snap in snapshots
        ]
        snapshots_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        return {
            "manifest_path": manifest_path,
            "snapshots_path": snapshots_path,
        }

    @classmethod
    def load_dataset(
        cls,
        output_dir: Path | str,
    ) -> tuple[list[EvidenceStateSnapshot], DatasetManifest]:
        """
        Loads `(snapshots, manifest)` previously saved via `save_dataset`.
        """
        target_dir = Path(output_dir)
        manifest_path = target_dir / "manifest.json"
        snapshots_path = target_dir / "snapshots.jsonl"

        manifest = DatasetManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        snapshots: list[EvidenceStateSnapshot] = []
        for raw_line in snapshots_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line:
                snapshots.append(EvidenceStateSnapshot.model_validate_json(line))

        return snapshots, manifest


def generate_dataset(
    total_cases: int = 240,
    master_seed: int = 2026,
    hard_case_ratio: float = 0.10,
    num_orderings: int = 2,
    stage_fractions: tuple[float, ...] = DatasetGenerator.DEFAULT_STAGE_FRACTIONS,
    templates_dir: Optional[Path | str] = None,
) -> tuple[list[EvidenceStateSnapshot], DatasetManifest]:
    """Module-level wrapper for DatasetGenerator.generate_dataset()."""
    return DatasetGenerator.generate_dataset(
        total_cases=total_cases,
        master_seed=master_seed,
        hard_case_ratio=hard_case_ratio,
        num_orderings=num_orderings,
        stage_fractions=stage_fractions,
        templates_dir=templates_dir,
    )


def save_dataset(
    snapshots: list[EvidenceStateSnapshot],
    manifest: DatasetManifest,
    output_dir: Path | str,
) -> dict[str, Path]:
    """Module-level wrapper for DatasetGenerator.save_dataset()."""
    return DatasetGenerator.save_dataset(
        snapshots=snapshots,
        manifest=manifest,
        output_dir=output_dir,
    )

