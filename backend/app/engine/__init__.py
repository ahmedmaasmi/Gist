# backend/app/engine/__init__.py
from app.engine.consistency import StructuredConsistencyEngine
from app.engine.dataset_generator import (
    DatasetGenerator,
    DatasetManifest,
    generate_dataset,
    save_dataset,
)
from app.engine.observation import ObservationModel
from app.engine.reveal_sampler import (
    EvidenceRevealSampler,
    EvidenceStateSnapshot,
    sample_reveal_snapshots,
)
from app.engine.simulator import SocialSimulator
from app.engine.solver import (
    CaseSolvabilityValidator,
    CaseValidationReport,
    SymbolicTimelineSolver,
)
from app.engine.templates import (
    SampledCaseSetup,
    TemplateRegistry,
    generate_valid_case,
    get_template,
    get_templates_by_split,
    load_all_templates,
    sample_case_setup_from_template,
)

__all__ = [
    "StructuredConsistencyEngine",
    "ObservationModel",
    "SocialSimulator",
    "SymbolicTimelineSolver",
    "CaseValidationReport",
    "CaseSolvabilityValidator",
    "SampledCaseSetup",
    "TemplateRegistry",
    "load_all_templates",
    "get_template",
    "get_templates_by_split",
    "sample_case_setup_from_template",
    "generate_valid_case",
    "EvidenceStateSnapshot",
    "EvidenceRevealSampler",
    "sample_reveal_snapshots",
    "DatasetManifest",
    "DatasetGenerator",
    "generate_dataset",
    "save_dataset",
]
