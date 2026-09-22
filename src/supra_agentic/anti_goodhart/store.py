"""Persistence owned exclusively by the observer domain O."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from .records import Diagnostic, DiagnosticStatus, ObserverFailure

_DIAGNOSTIC_STATUSES = {"OBSERVED", "UNKNOWN", "NOT_EVALUATED", "CONFLICT"}
_PROCESS_LOCK_RETRY_SECONDS = 0.01


class ObserverStoreCorruptionError(RuntimeError):
    """Raised when persisted observer evidence is not valid appendable JSONL."""


@contextmanager
def _interprocess_file_lock(path: Path) -> Iterator[None]:
    """Serialize store mutations across independent observer processes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\\0")
            handle.flush()
        handle.seek(0)

        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(_PROCESS_LOCK_RETRY_SECONDS)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


class ObserverStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    @property
    def diagnostics_path(self) -> Path:
        return self.root / "diagnostics.jsonl"

    @property
    def lock_path(self) -> Path:
        return self.root / ".observer_store.lock"

    @property
    def failures_path(self) -> Path:
        return self.root / "observer_failures.jsonl"

    def _read_records(
        self,
        path: Path,
        *,
        validate_diagnostics: bool = False,
    ) -> list[dict[str, Any]]:
        """Read JSONL strictly so corruption cannot masquerade as missing evidence."""
        if not path.exists():
            return []
        raw = path.read_bytes()
        if not raw:
            return []
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ObserverStoreCorruptionError(
                f"{path.name} contains invalid UTF-8"
            ) from exc

        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                raise ObserverStoreCorruptionError(
                    f"{path.name} contains an empty JSONL record at line {line_number}"
                )
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ObserverStoreCorruptionError(
                    f"{path.name} contains invalid JSON at line {line_number}"
                ) from exc
            if not isinstance(decoded, dict):
                raise ObserverStoreCorruptionError(
                    f"{path.name} contains a non-object record at line {line_number}"
                )
            item = cast(dict[str, Any], decoded)
            if validate_diagnostics and self._validated_diagnostic(item) is None:
                raise ObserverStoreCorruptionError(
                    f"{path.name} contains an invalid diagnostic at line {line_number}"
                )
            records.append(item)
        return records

    @staticmethod
    def _validated_diagnostic(item: dict[str, Any]) -> Diagnostic | None:
        string_fields = (
            "diagnostic_id",
            "detector_id",
            "detector_version",
            "trace_sha256",
            "kind",
            "status",
            "message",
        )
        if not all(isinstance(item.get(key), str) for key in string_fields):
            return None
        status = item["status"]
        details = item.get("details")
        if status not in _DIAGNOSTIC_STATUSES or not isinstance(details, dict):
            return None
        try:
            diagnostic = Diagnostic(
                detector_id=item["detector_id"],
                detector_version=item["detector_version"],
                trace_sha256=item["trace_sha256"],
                kind=item["kind"],
                status=cast(DiagnosticStatus, status),
                message=item["message"],
                details=cast(dict[str, Any], details),
            )
            diagnostic_id = diagnostic.diagnostic_id
        except (TypeError, ValueError):
            return None
        if diagnostic_id != item["diagnostic_id"]:
            return None
        return diagnostic

    def read_diagnostics(self) -> list[dict[str, Any]]:
        return self._read_records(self.diagnostics_path, validate_diagnostics=True)

    def read_failures(self) -> list[dict[str, Any]]:
        return self._read_records(self.failures_path)

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        """Append one record without ever concatenating onto an existing JSON object."""
        needs_separator = False
        if path.exists() and path.stat().st_size:
            with path.open("rb") as existing:
                existing.seek(-1, os.SEEK_END)
                needs_separator = existing.read(1) != b"\n"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            if needs_separator:
                handle.write("\n")
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            )

    def append_diagnostic(self, diagnostic: Diagnostic) -> bool:
        with self._lock, _interprocess_file_lock(self.lock_path):
            existing = {
                str(item.get("diagnostic_id") or "") for item in self.read_diagnostics()
            }
            if diagnostic.diagnostic_id in existing:
                return False
            self.root.mkdir(parents=True, exist_ok=True)
            self._append_jsonl(self.diagnostics_path, diagnostic.to_record())
            return True

    def append_failure(self, failure: ObserverFailure) -> None:
        with self._lock, _interprocess_file_lock(self.lock_path):
            # Validate existing framing before mutation; never worsen a corrupt ledger.
            self.read_failures()
            self.root.mkdir(parents=True, exist_ok=True)
            self._append_jsonl(self.failures_path, failure.to_record())
