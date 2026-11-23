"""Backend registry; third-party adapters are discovered through package entry points."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from threading import Event
from typing import Protocol

from .contracts import RunResult, RunSpec
from .store import FilesystemArtifactStore


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Per-attempt workspace, artifact writer, deadline and cooperative cancel signal."""

    attempt_number: int
    workspace: Path
    artifacts: FilesystemArtifactStore
    deadline_monotonic: float | None
    cancel_event: Event

    @property
    def cancellation_requested(self) -> bool:
        return self.cancel_event.is_set()

    @property
    def deadline_expired(self) -> bool:
        import time

        return (
            self.deadline_monotonic is not None
            and time.monotonic() >= self.deadline_monotonic
        )


class ExperimentBackend(Protocol):
    backend_id: str
    backend_version: str
    thread_safe: bool

    def validate(self, run: RunSpec) -> Sequence[str]: ...

    def execute(self, run: RunSpec, context: ExecutionContext) -> RunResult: ...


BackendFactory = Callable[[], ExperimentBackend]


def available_backends() -> tuple[str, ...]:
    names = {"demo"}
    names.update(point.name for point in entry_points(group="simops.backends"))
    return tuple(sorted(names))


def load_backend(backend_id: str) -> ExperimentBackend:
    if backend_id == "demo":
        from .demo import DemoNavigationBackend

        return DemoNavigationBackend()
    matches = [point for point in entry_points(group="simops.backends") if point.name == backend_id]
    if not matches:
        raise ValueError(
            f"unknown backend {backend_id!r}; installed backends: {', '.join(available_backends())}"
        )
    if len(matches) > 1:
        raise ValueError(f"more than one installed adapter claims backend ID {backend_id!r}")
    loaded = matches[0].load()
    instance = loaded() if isinstance(loaded, type) else loaded
    for attribute in ("backend_id", "backend_version", "thread_safe", "validate", "execute"):
        if not hasattr(instance, attribute):
            raise TypeError(f"backend {backend_id!r} does not define {attribute}")
    if instance.backend_id != backend_id:
        raise ValueError(
            f"entry point {backend_id!r} loaded backend declaring ID {instance.backend_id!r}"
        )
    return instance
