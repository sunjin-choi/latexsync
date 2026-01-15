"""State persistence for 3-way merge and conflict detection.
This module stores per-section base items and hashes on disk.
The syncer uses it to detect edits and resolve merges.
State is kept separate from parsing and rendering concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .ir import SectionKey


@dataclass(frozen=True)
class SectionState:
    """Per-section sync state snapshot."""
    base_items: list[str]
    md_hash: str
    tex_hash: str
    md_count: int
    tex_count: int


@dataclass
class SyncState:
    """Container for all section states."""
    sections: dict[str, SectionState]


@dataclass
class StateLoadResult:
    """Result bundle for state loading."""
    state: SyncState
    errors: list[str]
    warnings: list[str]


def load_state(path: Path) -> StateLoadResult:
    """Load sync state from disk, returning warnings on missing files."""
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        warnings.append(f"State not found, starting fresh: {path}")
        return StateLoadResult(SyncState(sections={}), errors, warnings)
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except OSError as exc:
        errors.append(f"Failed to read state: {exc}")
        return StateLoadResult(SyncState(sections={}), errors, warnings)
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in state: {exc}")
        return StateLoadResult(SyncState(sections={}), errors, warnings)

    if not isinstance(data, dict):
        errors.append("State root must be an object")
        return StateLoadResult(SyncState(sections={}), errors, warnings)

    raw_sections = data.get("sections")
    if not isinstance(raw_sections, dict):
        warnings.append("Missing sections in state; starting fresh")
        return StateLoadResult(SyncState(sections={}), errors, warnings)

    sections: dict[str, SectionState] = {}
    for key, raw_val in raw_sections.items():
        if not isinstance(key, str) or not isinstance(raw_val, dict):
            continue
        base_items = _get_str_list(raw_val.get("base_items")) or []
        md_hash = _get_str(raw_val.get("md_hash"))
        tex_hash = _get_str(raw_val.get("tex_hash"))
        md_count = _get_int(raw_val.get("md_count"))
        tex_count = _get_int(raw_val.get("tex_count"))
        if md_hash is None or tex_hash is None or md_count is None or tex_count is None:
            continue
        sections[key] = SectionState(
            base_items=base_items,
            md_hash=md_hash,
            tex_hash=tex_hash,
            md_count=md_count,
            tex_count=tex_count,
        )

    return StateLoadResult(SyncState(sections=sections), errors, warnings)


def save_state(path: Path, state: SyncState) -> list[str]:
    """Persist sync state to disk and return any errors."""
    errors: list[str] = []
    data = {"sections": {}}
    for key, section in state.sections.items():
        data["sections"][key] = {
            "base_items": list(section.base_items),
            "md_hash": section.md_hash,
            "tex_hash": section.tex_hash,
            "md_count": section.md_count,
            "tex_count": section.tex_count,
        }
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        errors.append(f"Failed to write state: {exc}")
    return errors


def serialize_section(section: SectionKey) -> str:
    """Serialize a section key tuple into a stable string."""
    return "::".join(section)


def deserialize_section(key: str) -> SectionKey:
    """Deserialize a section key string into a tuple."""
    if not key:
        return tuple()
    return tuple(key.split("::"))


def _get_str(value: object) -> str | None:
    """Return the string value if the input is a string."""
    return value if isinstance(value, str) else None


def _get_int(value: object) -> int | None:
    """Return the integer value if the input is an int."""
    return value if isinstance(value, int) else None


def _get_str_list(value: object) -> list[str] | None:
    """Return a list of strings if the input matches the shape."""
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        result.append(item)
    return result
