"""Configuration loading and defaults for md/tex sync.
The config defines file paths, section mapping, and figure patterns.
Sync orchestration uses this module to resolve inputs and defaults.
Other modules read these settings but do not parse JSON directly.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class FigureMapping:
    """Configurable patterns and templates for figure mapping."""
    md_pattern: str
    tex_pattern: str
    md_template: str
    tex_template: str


DEFAULT_FIGURE_MAPPING = FigureMapping(
    md_pattern=r"!\[\[(?P<path>[^\]|]+)(?:\|(?P<caption>[^\]]+))?\]\]",
    tex_pattern=(
        r"\\begin\{figure\}.*?"
        r"\\includegraphics(?:\[[^\]]*\])?\{(?P<path>[^}]+)\}.*?"
        r"(?:\\caption\{(?P<caption>[^}]*)\})?.*?"
        r"\\end\{figure\}"
    ),
    md_template="![[{path}|{caption}]]",
    tex_template=(
        "\\begin{{figure}}[h]\n"
        "\\centering\n"
        "\\includegraphics{{{path}}}\n"
        "\\caption{{{caption}}}\n"
        "\\end{{figure}}"
    ),
)


@dataclass(frozen=True)
class SyncConfig:
    """Top-level sync configuration loaded from JSON."""
    markdown_path: Path
    tex_root: Path
    heading_to_section: dict[str, str]
    figure_mapping: FigureMapping


@dataclass
class ConfigLoadResult:
    """Result bundle for config loading."""
    config: SyncConfig | None
    errors: list[str]
    warnings: list[str]


def load_config(path: Path) -> ConfigLoadResult:
    """Load and validate the sync configuration JSON."""
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        errors.append(f"Config not found: {path}")
        return ConfigLoadResult(None, errors, warnings)
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except OSError as exc:
        errors.append(f"Failed to read config: {exc}")
        return ConfigLoadResult(None, errors, warnings)
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in config: {exc}")
        return ConfigLoadResult(None, errors, warnings)

    if not isinstance(data, dict):
        errors.append("Config root must be an object")
        return ConfigLoadResult(None, errors, warnings)

    md_path = _get_str(data.get("markdown_path"))
    tex_root = _get_str(data.get("tex_root"))
    heading_map = _get_str_dict(data.get("heading_to_section"))

    if md_path is None:
        errors.append("Missing or invalid markdown_path")
    if tex_root is None:
        errors.append("Missing or invalid tex_root")
    if heading_map is None:
        errors.append("Missing or invalid heading_to_section")

    if errors:
        return ConfigLoadResult(None, errors, warnings)

    base_dir = path.parent
    md_full = Path(md_path)
    tex_full = Path(tex_root)
    if not md_full.is_absolute():
        md_full = base_dir / md_full
    if not tex_full.is_absolute():
        tex_full = base_dir / tex_full

    figure_mapping = _load_figure_mapping(data.get("figure_mapping"), warnings)

    config = SyncConfig(
        markdown_path=md_full,
        tex_root=tex_full,
        heading_to_section=heading_map,
        figure_mapping=figure_mapping,
    )
    return ConfigLoadResult(config, errors, warnings)


def _load_figure_mapping(raw: object, warnings: list[str]) -> FigureMapping:
    """Load a figure mapping with defaults and warnings."""
    if raw is None:
        return DEFAULT_FIGURE_MAPPING
    if not isinstance(raw, dict):
        warnings.append("figure_mapping must be an object; using defaults")
        return DEFAULT_FIGURE_MAPPING
    md_pattern = _get_str(raw.get("md_pattern")) or DEFAULT_FIGURE_MAPPING.md_pattern
    tex_pattern = _get_str(raw.get("tex_pattern")) or DEFAULT_FIGURE_MAPPING.tex_pattern
    md_template = _get_str(raw.get("md_template")) or DEFAULT_FIGURE_MAPPING.md_template
    tex_template = _get_str(raw.get("tex_template")) or DEFAULT_FIGURE_MAPPING.tex_template
    return FigureMapping(
        md_pattern=md_pattern,
        tex_pattern=tex_pattern,
        md_template=md_template,
        tex_template=tex_template,
    )


def _get_str(value: object) -> str | None:
    """Return the string value if the input is a string."""
    return value if isinstance(value, str) else None


def _get_str_dict(value: object) -> dict[str, str] | None:
    """Return a string-to-string dict if input matches the shape."""
    if not isinstance(value, dict):
        return None
    result: dict[str, str] = {}
    for key, val in value.items():
        if not isinstance(key, str) or not isinstance(val, str):
            return None
        result[key] = val
    return result
