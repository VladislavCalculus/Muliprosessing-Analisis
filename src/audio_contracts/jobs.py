"""Small, pickle-compatible descriptors for file-processing jobs."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike, fspath
from pathlib import Path
from typing import Literal


def _nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _identity(source_id: str, source_name: str | None, schema_version: int) -> None:
    _nonempty(source_id, "source_id")
    if source_name is not None:
        _nonempty(source_name, "source_name")
    if type(schema_version) is not int or schema_version != 1:
        raise ValueError("unsupported job schema_version")


@dataclass(frozen=True, slots=True)
class FileJob:
    """One source selected by the parent; no audio array crosses this boundary.

    Paths are resolved while creating the descriptor, before another process can
    observe a different working directory. The file need not exist yet: missing
    files are per-job read failures, not constructor failures.
    """

    source_id: str
    path: str | PathLike[str]
    source_name: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _identity(self.source_id, self.source_name, self.schema_version)
        path = fspath(self.path)
        if not isinstance(path, str):
            raise TypeError("path must be a string or a text path-like object")
        if not path.strip():
            raise ValueError("path must not be empty")
        object.__setattr__(self, "path", Path(path).expanduser().resolve())


@dataclass(frozen=True, slots=True)
class JobError:
    """Serializable read, processing, or worker failure for a single source."""

    source_id: str
    error_code: str
    message: str
    stage: Literal["read", "process", "worker"]
    source_name: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _identity(self.source_id, self.source_name, self.schema_version)
        _nonempty(self.error_code, "error_code")
        _nonempty(self.message, "message")
        if self.stage not in ("read", "process", "worker"):
            raise ValueError("stage must be 'read', 'process', or 'worker'")
