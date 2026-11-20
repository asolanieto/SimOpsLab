"""Domain-neutral contracts for simulation and system experiments."""

from .backends import ExecutionContext, ExperimentBackend, available_backends, load_backend
from .contracts import (
    ArtifactRef,
    CampaignSpec,
    MetricState,
    MetricValue,
    RunResult,
    RunSpec,
    RunStatus,
    SystemOutcome,
)
from .manifest import LoadedCampaign, load_campaign_manifest
from .optimization import (
    CandidateResult,
    ConstraintSpec,
    Direction,
    EvaluationStatus,
    LatinHypercubeSearch,
    ObjectiveSpec,
    OptimizationResult,
    ParameterKind,
    ParameterSpec,
    TuningEvaluation,
    TuningSpec,
    latin_hypercube_sample,
    pareto_front,
)
from .planner import (
    CampaignMatrix,
    ConfigurationDefinition,
    PlanningError,
    ScenarioDefinition,
    plan_campaign,
)
from .runner import CampaignRunner, CampaignValidationError
from .store import CampaignConflictError, FilesystemArtifactStore, SQLiteCampaignStore
from .tuning import TuningManifest, load_tuning_manifest, run_tuning

__all__ = [
    "ArtifactRef",
    "CampaignMatrix",
    "CampaignConflictError",
    "CampaignRunner",
    "CampaignValidationError",
    "CampaignSpec",
    "CandidateResult",
    "ConfigurationDefinition",
    "ConstraintSpec",
    "Direction",
    "ExecutionContext",
    "ExperimentBackend",
    "FilesystemArtifactStore",
    "EvaluationStatus",
    "LatinHypercubeSearch",
    "MetricState",
    "MetricValue",
    "LoadedCampaign",
    "ObjectiveSpec",
    "OptimizationResult",
    "ParameterKind",
    "ParameterSpec",
    "PlanningError",
    "RunResult",
    "RunSpec",
    "RunStatus",
    "ScenarioDefinition",
    "SystemOutcome",
    "SQLiteCampaignStore",
    "TuningEvaluation",
    "TuningManifest",
    "TuningSpec",
    "latin_hypercube_sample",
    "load_backend",
    "load_campaign_manifest",
    "load_tuning_manifest",
    "available_backends",
    "run_tuning",
    "pareto_front",
    "plan_campaign",
]
