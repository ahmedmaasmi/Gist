# backend/app/engine/dataset_generator.py
"""
PRD Sections 8.1-8.4 and 10.3: build the versioned training/evaluation dataset.

Run:  make dataset   (or: cd backend && uv run python -m app.engine.dataset_generator --out ../data/generated)

Splits (PRD 8.4, D-018, D-020):
  * cases on 'dev' templates are split BY CASE into train / val / test_in_dist (70 / 15 / 15 per template);
  * every case on a held-out template goes to test_held_out_template;
  * test_ood_shifted: extra cases on held-out templates with variables OUTSIDE the training ranges;
  * train cases carry a grouped-CV fold (group = template) for hyperparameter tuning (step 7).
All evidence states (snapshots) of a case share its split.

NOTE: scores on this synthetic data measure recovery of the generator's logic (PRD 1).
"""
import argparse
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from app.domain.setting import SettingTemplate
from app.domain.simulation import SimulatedCaseBundle
from app.engine.reveal_sampler import EvidenceRevealSampler, EvidenceStateSnapshot
from app.engine.solver import CaseSolvabilityValidator, CaseValidationReport
from app.engine.templates import (
    CASE_VARIABLE_RANGES,
    SHIFTED_CASE_VARIABLE_RANGES,
    TemplateRegistry,
    sample_case_setup_from_template,
)
from app.features import FEATURE_SPEC_VERSION, FEATURES, compute_suspect_features

DATASET_VERSION = "0.2.0"
# Share of each dev template's cases per split (PRD 8.4); the rest is train.
DEV_SPLIT_FRACTIONS = {"val": 0.15, "test_in_dist": 0.15}
NUM_CV_FOLDS = 3
SPLITS = ("train", "val", "test_in_dist", "test_held_out_template", "test_ood_shifted")
FEATURE_TABLE_KEYS = (
    "case_id",
    "template_id",
    "split",
    "cv_fold",
    "difficulty",
    "order_idx",
    "stage_idx",
    "reveal_fraction",
    "suspect_id",
    "label",
)


class DatasetManifest(BaseModel):
    """
    PRD 8.1 & 10.3: everything needed to reproduce and honestly describe the dataset,
    including BOTH the number of templates and the number of generated cases.
    """

    dataset_version: str = DATASET_VERSION
    feature_spec_version: str = FEATURE_SPEC_VERSION
    git_commit: str = "unknown"
    master_seed: int
    num_templates_total: int = Field(..., ge=1)
    templates_by_group: dict[str, list[str]] = Field(default_factory=dict)
    cv_folds: dict[str, list[str]] = Field(default_factory=dict, description="fold -> dev templates")
    num_cases_total: int = Field(..., ge=1)
    cases_by_split: dict[str, int] = Field(default_factory=dict)
    snapshots_by_split: dict[str, int] = Field(default_factory=dict)
    feature_rows_by_split: dict[str, int] = Field(default_factory=dict)
    difficulty_by_split: dict[str, dict[str, int]] = Field(default_factory=dict)
    case_variable_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)
    shifted_variable_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)
    generator_params: dict[str, float | int | list[float]] = Field(default_factory=dict)
    checksums: dict[str, str] = Field(default_factory=dict, description="sha256 of the written files")
    note: str = "Synthetic-data scores measure recovery of the generator's logic, not real-world skill."


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class DatasetGenerator:
    DEFAULT_STAGE_FRACTIONS: tuple[float, ...] = (0.35, 0.65, 1.0)

    @staticmethod
    def _generate_validated_case(
        template: SettingTemplate,
        case_id: str,
        base_seed: int,
        variable_ranges: dict[str, tuple[float, float]],
        max_attempts: int = 25,
    ) -> tuple[SimulatedCaseBundle, CaseValidationReport]:
        """
        Re-rolls sub-seeds until solvability checks 1-3 pass. Check 4 only labels difficulty (D-010),
        so no filter here favours cases that a simple rule can solve.
        """
        report: CaseValidationReport | None = None
        for offset in range(max_attempts):
            setup = sample_case_setup_from_template(
                template=template, seed=base_seed + offset, variable_ranges=variable_ranges
            )
            setup.config.case_id = case_id
            bundle = setup.simulate()
            report = CaseSolvabilityValidator.validate_case(
                bundle=bundle, setting=bundle.setting, allow_hard_cases=True
            )
            if report.is_valid:
                return bundle, report
        raise RuntimeError(
            f"No valid case for '{case_id}' after {max_attempts} attempts: "
            f"{report.failure_reasons if report else 'no attempt'}"
        )

    @classmethod
    def generate_dataset(
        cls,
        total_cases: int = 1500,
        master_seed: int = 2026,
        ood_shifted_cases: int = 150,
        num_orderings: int = 2,
        stage_fractions: tuple[float, ...] = DEFAULT_STAGE_FRACTIONS,
        templates_dir: Path | str | None = None,
    ) -> tuple[list[EvidenceStateSnapshot], DatasetManifest]:
        """
        Generates `total_cases` cases spread evenly over all templates, plus `ood_shifted_cases`
        on the held-out templates with shifted variables, and slices every case into evidence states.
        """
        if total_cases < 1:
            raise ValueError(f"total_cases must be >= 1 (got {total_cases}).")
        templates = TemplateRegistry.load_all_templates(templates_dir=templates_dir)
        ordered = [templates[k] for k in sorted(templates)]
        dev = [t for t in ordered if t.split_group == "dev"]
        held_out = [t for t in ordered if t.split_group == "test_held_out_template"]
        fold_of = {t.template_id: i % NUM_CV_FOLDS for i, t in enumerate(dev)}

        # Case plan: (template, split, variable ranges)
        plan: list[tuple[SettingTemplate, str, dict[str, tuple[float, float]]]] = []
        for idx, tpl in enumerate(ordered):
            n = total_cases // len(ordered) + (1 if idx < total_cases % len(ordered) else 0)
            n_val = round(n * DEV_SPLIT_FRACTIONS["val"])
            n_test = round(n * DEV_SPLIT_FRACTIONS["test_in_dist"])
            for i in range(n):
                if tpl.split_group == "test_held_out_template":
                    split = "test_held_out_template"
                elif i < n - n_val - n_test:
                    split = "train"
                elif i < n - n_test:
                    split = "val"
                else:
                    split = "test_in_dist"
                plan.append((tpl, split, CASE_VARIABLE_RANGES))
        for i in range(ood_shifted_cases if held_out else 0):
            plan.append((held_out[i % len(held_out)], "test_ood_shifted", SHIFTED_CASE_VARIABLE_RANGES))

        snapshots: list[EvidenceStateSnapshot] = []
        cases_by_split = dict.fromkeys(SPLITS, 0)
        snapshots_by_split = dict.fromkeys(SPLITS, 0)
        difficulty_by_split: dict[str, dict[str, int]] = {s: {} for s in SPLITS}

        for case_idx, (tpl, split, ranges) in enumerate(plan):
            case_id = f"case_{tpl.template_id}_{case_idx:05d}"
            bundle, report = cls._generate_validated_case(
                tpl, case_id, base_seed=master_seed * 100_000 + case_idx * 100, variable_ranges=ranges
            )
            fold = fold_of.get(tpl.template_id) if split == "train" else None
            case_snaps = EvidenceRevealSampler.sample_reveal_snapshots(
                bundle=bundle,
                template=tpl,
                split=split,
                num_orderings=num_orderings,
                stage_fractions=stage_fractions,
                is_under_determined_hard_case=report.is_under_determined_hard_case,
            )
            snapshots.extend(
                s.model_copy(
                    update={"cv_fold": fold, "difficulty": report.difficulty_estimate, "setting": bundle.setting}
                )
                for s in case_snaps
            )
            cases_by_split[split] += 1
            snapshots_by_split[split] += len(case_snaps)
            difficulty_by_split[split][report.difficulty_estimate] = (
                difficulty_by_split[split].get(report.difficulty_estimate, 0) + 1
            )

        cv_folds: dict[str, list[str]] = {}
        for tid, fold in fold_of.items():
            cv_folds.setdefault(str(fold), []).append(tid)

        manifest = DatasetManifest(
            git_commit=_git_commit(),
            master_seed=master_seed,
            num_templates_total=len(ordered),
            templates_by_group={
                "dev": [t.template_id for t in dev],
                "test_held_out_template": [t.template_id for t in held_out],
            },
            cv_folds=cv_folds,
            num_cases_total=len(plan),
            cases_by_split=cases_by_split,
            snapshots_by_split=snapshots_by_split,
            difficulty_by_split=difficulty_by_split,
            case_variable_ranges=CASE_VARIABLE_RANGES,
            shifted_variable_ranges=SHIFTED_CASE_VARIABLE_RANGES,
            generator_params={
                "total_cases": total_cases,
                "ood_shifted_cases": ood_shifted_cases,
                "num_orderings": num_orderings,
                "stage_fractions": list(stage_fractions),
                "num_cv_folds": NUM_CV_FOLDS,
                "dev_val_fraction": DEV_SPLIT_FRACTIONS["val"],
                "dev_test_in_dist_fraction": DEV_SPLIT_FRACTIONS["test_in_dist"],
            },
        )
        return snapshots, manifest

    @staticmethod
    def feature_rows(snapshots: list[EvidenceStateSnapshot]) -> list[dict[str, object]]:
        """
        One row per suspect per evidence state (PRD 8.3). Features come only from T0, T1 and the map
        (compute_suspect_features); `label` comes from T3 and is an evaluation target, never a feature.
        """
        rows: list[dict[str, object]] = []
        for snap in snapshots:
            for row in compute_suspect_features(snap.t0_public, snap.t1_partial, snap.setting):
                rows.append(
                    {
                        "case_id": snap.case_id,
                        "template_id": snap.template_id,
                        "split": snap.split,
                        "cv_fold": "" if snap.cv_fold is None else snap.cv_fold,
                        "difficulty": snap.difficulty or "",
                        "order_idx": snap.order_idx,
                        "stage_idx": snap.stage_idx,
                        "reveal_fraction": snap.reveal_fraction,
                        "suspect_id": row.suspect_id,
                        "label": int(row.suspect_id == snap.culprit_id),
                        **row.features,
                    }
                )
        return rows

    @classmethod
    def save_dataset(
        cls,
        snapshots: list[EvidenceStateSnapshot],
        manifest: DatasetManifest,
        output_dir: Path | str,
    ) -> dict[str, Path]:
        """Writes snapshots.jsonl, features.csv and manifest.json (with sha256 checksums)."""
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)

        snapshots_text = "".join(
            json.dumps(s.model_dump(mode="json"), sort_keys=True) + "\n" for s in snapshots
        )
        rows = cls.feature_rows(snapshots)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[*FEATURE_TABLE_KEYS, *(f.name for f in FEATURES)])
        writer.writeheader()
        writer.writerows(rows)
        features_text = buf.getvalue()

        feature_rows_by_split = dict.fromkeys(SPLITS, 0)
        for row in rows:
            feature_rows_by_split[str(row["split"])] += 1
        manifest = manifest.model_copy(
            update={
                "feature_rows_by_split": feature_rows_by_split,
                "checksums": {
                    "snapshots.jsonl": hashlib.sha256(snapshots_text.encode()).hexdigest(),
                    "features.csv": hashlib.sha256(features_text.encode()).hexdigest(),
                },
            }
        )
        paths = {
            "snapshots_path": target / "snapshots.jsonl",
            "features_path": target / "features.csv",
            "manifest_path": target / "manifest.json",
        }
        paths["snapshots_path"].write_text(snapshots_text, encoding="utf-8")
        paths["features_path"].write_text(features_text, encoding="utf-8")
        paths["manifest_path"].write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return paths

    @classmethod
    def load_dataset(cls, output_dir: Path | str) -> tuple[list[EvidenceStateSnapshot], DatasetManifest]:
        target = Path(output_dir)
        manifest = DatasetManifest.model_validate_json((target / "manifest.json").read_text(encoding="utf-8"))
        snapshots = [
            EvidenceStateSnapshot.model_validate_json(line)
            for line in (target / "snapshots.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return snapshots, manifest


def generate_dataset(**kwargs) -> tuple[list[EvidenceStateSnapshot], DatasetManifest]:
    """Module-level wrapper for DatasetGenerator.generate_dataset()."""
    return DatasetGenerator.generate_dataset(**kwargs)


def save_dataset(
    snapshots: list[EvidenceStateSnapshot], manifest: DatasetManifest, output_dir: Path | str
) -> dict[str, Path]:
    """Module-level wrapper for DatasetGenerator.save_dataset()."""
    return DatasetGenerator.save_dataset(snapshots, manifest, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=1500)
    parser.add_argument("--ood-shifted", type=int, default=150)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=Path("../data/generated"))
    args = parser.parse_args()
    snapshots, manifest = DatasetGenerator.generate_dataset(
        total_cases=args.cases, master_seed=args.seed, ood_shifted_cases=args.ood_shifted
    )
    out_dir = args.out / f"v{DATASET_VERSION}"
    paths = DatasetGenerator.save_dataset(snapshots, manifest, out_dir)
    saved = DatasetManifest.model_validate_json(paths["manifest_path"].read_text(encoding="utf-8"))
    print(f"Wrote {out_dir}")
    print(json.dumps(
        {
            "cases": saved.num_cases_total,
            "templates": saved.num_templates_total,
            "cases_by_split": saved.cases_by_split,
            "feature_rows_by_split": saved.feature_rows_by_split,
            "cv_folds": saved.cv_folds,
            "checksums": saved.checksums,
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
