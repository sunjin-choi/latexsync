"""End-to-end sync orchestration using config, state, and parsers.
This module loads config/state, parses inputs, and performs merges.
It applies updates via markdown/latex modules and writes results.
Conflicts are detected at the section level and reported to callers.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
from pathlib import Path
import re

from .config import load_config
from .ir import SectionKey
from .latex import StaticBlock, SyncBlock, TexDocument, apply_tex_updates, parse_tex_file
from .markdown import MdDocument, apply_markdown_updates, parse_markdown
from .mappers import build_registry
from .registry import Registry
from .state import SectionState, SyncState, load_state, save_state, serialize_section


@dataclass(frozen=True)
class SyncResult:
    """Result bundle for a sync run."""
    updated_files: list[Path]
    warnings: list[str]
    errors: list[str]
    conflicts: list[str]


@dataclass(frozen=True)
class Edit:
    """Edit operation from a base list to a new list."""
    start: int
    end: int
    replacement: list[str]


@dataclass(frozen=True)
class MergeResult:
    """Merged list plus conflict details."""
    merged: list[str]
    conflicts: list[str]


def sync_project(
    config_path: Path | None = None,
    state_path: Path | None = None,
    force_md_to_tex: bool = False,
    force_tex_to_md: bool = False,
) -> SyncResult:
    """Run a sync pass using a 3-way merge against saved state.
    The function loads config/state, parses markdown and latex inputs,
    then merges section items using the last saved base snapshot.
    Updates are applied via markdown/latex modules and written to disk.
    Conflicts are collected and returned without partial writes.
    """
    updated_files: list[Path] = []
    warnings: list[str] = []
    errors: list[str] = []
    conflicts: list[str] = []

    config_path = config_path or Path("sync_config.json")
    state_path = state_path or Path("sync_state.json")

    config_result = load_config(config_path)
    warnings.extend(config_result.warnings)
    errors.extend(config_result.errors)
    if not config_result.config:
        return SyncResult(updated_files, warnings, errors, conflicts)
    config = config_result.config

    if force_md_to_tex and force_tex_to_md:
        errors.append("Both force flags set; choose one direction")
        return SyncResult(updated_files, warnings, errors, conflicts)

    state_result = load_state(state_path)
    warnings.extend(state_result.warnings)
    errors.extend(state_result.errors)
    state = state_result.state

    registry = build_registry(config.figure_mapping)

    md_doc = parse_markdown(config.markdown_path)
    warnings.extend(md_doc.warnings)
    if not md_doc.lines and any(msg.startswith("Failed to read markdown") for msg in md_doc.warnings):
        errors.append(f"Markdown file is unreadable: {config.markdown_path}")
        return SyncResult(updated_files, warnings, errors, conflicts)

    tex_docs = _load_tex_docs(config.heading_to_section, config.tex_root, warnings)

    md_items = md_doc.raw_items_by_section
    tex_items = _collect_tex_items(tex_docs)

    sections = set(md_items.keys()) | set(tex_items.keys())

    planned_md_updates: dict[SectionKey, list[str]] = {}
    planned_tex_updates: dict[SectionKey, list[str]] = {}
    state_updates: dict[SectionKey, SectionState] = {}
    skip_sections: set[SectionKey] = set()

    for section in sections:
        md_raw = md_items.get(section, [])
        tex_raw = tex_items.get(section, [])
        md_canon = [_canonical_from_md(registry, item) for item in md_raw]
        tex_canon = [_canonical_from_tex(registry, item) for item in tex_raw]

        state_key = serialize_section(section)
        prev_state = state.sections.get(state_key)
        base_items = prev_state.base_items if prev_state else []

        if force_md_to_tex:
            merged = md_canon
            if _can_update_tex(tex_docs, section, merged, warnings):
                planned_tex_updates[section] = [_render_md_to_tex(registry, item) for item in merged]
            else:
                skip_sections.add(section)
            state_updates[section] = _state_from_items(merged)
            continue

        if force_tex_to_md:
            merged = tex_canon
            if _can_update_md(md_doc, section, merged, warnings):
                planned_md_updates[section] = merged
            else:
                skip_sections.add(section)
            state_updates[section] = _state_from_items(merged)
            continue

        merge = _merge_lists(base_items, md_canon, tex_canon)
        if merge.conflicts:
            conflicts.extend(f"Conflict in section {section}: {detail}" for detail in merge.conflicts)
            skip_sections.add(section)
            continue

        merged = merge.merged
        if merged != md_canon:
            if _can_update_md(md_doc, section, merged, warnings):
                planned_md_updates[section] = merged
            else:
                skip_sections.add(section)
        if merged != tex_canon:
            if _can_update_tex(tex_docs, section, merged, warnings):
                planned_tex_updates[section] = [_render_md_to_tex(registry, item) for item in merged]
            else:
                skip_sections.add(section)

        state_updates[section] = _state_from_items(merged)

    if conflicts:
        return SyncResult(updated_files, warnings, errors, conflicts)

    updated_files.extend(_apply_tex_updates(tex_docs, planned_tex_updates, warnings))

    if planned_md_updates:
        updated_md_lines, md_warnings = apply_markdown_updates(md_doc, planned_md_updates)
        warnings.extend(md_warnings)
        updated_text = "".join(updated_md_lines)
        original_text = "".join(md_doc.lines)
        if updated_text != original_text:
            try:
                config.markdown_path.write_text(updated_text, encoding="utf-8")
                updated_files.append(config.markdown_path)
            except OSError as exc:
                errors.append(f"Failed to write markdown: {exc}")

    if state_updates:
        new_state = SyncState(sections=dict(state.sections))
        for section, updated in state_updates.items():
            if section in skip_sections:
                continue
            new_state.sections[serialize_section(section)] = updated
        errors.extend(save_state(state_path, new_state))

    return SyncResult(updated_files, warnings, errors, conflicts)


def _load_tex_docs(
    heading_to_section: dict[str, str],
    tex_root: Path,
    warnings: list[str],
) -> dict[str, TexDocument]:
    """Load all latex section files defined by heading mapping.
    Each heading maps to a latex file under the configured root.
    Parse warnings are accumulated for later reporting.
    """
    tex_docs: dict[str, TexDocument] = {}
    for heading, name in heading_to_section.items():
        tex_path = _resolve_tex_path(tex_root, name)
        doc = parse_tex_file(tex_path, base_section=heading)
        warnings.extend(doc.warnings)
        tex_docs[heading] = doc
    return tex_docs


def _resolve_tex_path(tex_root: Path, name: str) -> Path:
    """Resolve a latex file path from root and name."""
    path = Path(name)
    if not path.suffix:
        path = path.with_suffix(".tex")
    if not path.is_absolute():
        path = tex_root / path
    return path


def _collect_tex_items(docs: dict[str, TexDocument]) -> dict[SectionKey, list[str]]:
    """Collect syncable paragraph texts grouped by section.
    Text is drawn from syncable blocks only (comment-free paragraphs).
    """
    items: dict[SectionKey, list[str]] = {}
    for doc in docs.values():
        for section, texts in doc.raw_text_by_section.items():
            items.setdefault(section, []).extend(texts)
    return items


def _canonical_from_md(registry: Registry, text: str) -> str:
    """Normalize markdown text into canonical markdown via IR.
    Each line is normalized independently to preserve paragraph structure.
    Parsing and re-rendering stabilizes formatting for comparisons.
    """
    lines = _split_lines(text)
    normalized = [_render_md_canonical(registry, line) for line in lines]
    return "\n".join(normalized).strip()


def _canonical_from_tex(registry: Registry, text: str) -> str:
    """Normalize latex text into canonical markdown via IR.
    Each line is normalized independently to preserve paragraph structure.
    Latex is parsed into IR and rendered as markdown for comparison.
    """
    lines = _split_lines(text)
    normalized = [_render_tex_canonical(registry, line) for line in lines]
    return "\n".join(normalized).strip()


def _render_md_to_tex(registry: Registry, text: str) -> str:
    """Render markdown text into latex via IR.
    Text is rendered line-by-line to preserve paragraph structure.
    """
    lines = _split_lines(text)
    rendered = [_render_md_latex(registry, line) for line in lines]
    return "\n".join(rendered).strip()


def _hash_items(items: list[str]) -> str:
    """Hash normalized items for change detection.
    Whitespace is collapsed before hashing to reduce noise.
    """
    normalized = "\n".join(_normalize_item(item) for item in items).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _normalize_item(text: str) -> str:
    """Collapse whitespace to stabilize diff matching."""
    return re.sub(r"\s+", " ", text.strip())


def _split_lines(text: str) -> list[str]:
    """Split a paragraph string into logical lines without trailing empties."""
    if text == "":
        return [""]
    return text.splitlines()


def _render_md_canonical(registry: Registry, text: str) -> str:
    """Render markdown text into normalized markdown via IR."""
    nodes = registry.parse_md_block(text.strip())
    return registry.render_md(nodes).strip()


def _render_tex_canonical(registry: Registry, text: str) -> str:
    """Render latex text into normalized markdown via IR."""
    nodes = registry.parse_tex_block(text.strip())
    return registry.render_md(nodes).strip()


def _render_md_latex(registry: Registry, text: str) -> str:
    """Render markdown text into latex via IR."""
    nodes = registry.parse_md_block(text.strip())
    return registry.render_tex(nodes).strip()


def _diff_edits(base: list[str], other: list[str]) -> list[Edit]:
    """Compute edit operations from base to other.
    SequenceMatcher produces replace/insert/delete opcodes.
    These are captured as edits for later 3-way merging.
    """
    base_norm = [_normalize_item(item) for item in base]
    other_norm = [_normalize_item(item) for item in other]
    matcher = difflib.SequenceMatcher(a=base_norm, b=other_norm)
    edits: list[Edit] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        edits.append(Edit(start=i1, end=i2, replacement=other[j1:j2]))
    return edits


def _merge_lists(base: list[str], md_items: list[str], tex_items: list[str]) -> MergeResult:
    """Merge MD and TeX edits against a base list.
    Non-overlapping edits are applied in order, preserving base text.
    Overlapping edits are reported as conflicts for the section.
    The result is a merged item list or a conflict list.
    """
    md_edits = _diff_edits(base, md_items)
    tex_edits = _diff_edits(base, tex_items)
    merged: list[str] = []
    conflicts: list[str] = []
    i_base = 0
    i_md = 0
    i_tex = 0
    while i_base <= len(base):
        md_edit = md_edits[i_md] if i_md < len(md_edits) else None
        tex_edit = tex_edits[i_tex] if i_tex < len(tex_edits) else None
        next_start = min(
            md_edit.start if md_edit else len(base),
            tex_edit.start if tex_edit else len(base),
        )
        if i_base < next_start:
            merged.extend(base[i_base:next_start])
            i_base = next_start
            continue

        md_here = md_edit is not None and md_edit.start == i_base
        tex_here = tex_edit is not None and tex_edit.start == i_base

        if md_here and tex_here:
            if _edits_identical(md_edit, tex_edit):
                merged.extend(md_edit.replacement)
            else:
                conflicts.append(f"overlap at base index {i_base}")
            i_base = max(md_edit.end, tex_edit.end)
            i_md += 1
            i_tex += 1
            continue
        if md_here:
            if tex_edit and _overlaps(md_edit, tex_edit):
                conflicts.append(f"overlap at base index {i_base}")
                i_base = max(md_edit.end, tex_edit.end)
                i_md += 1
                i_tex += 1
                continue
            merged.extend(md_edit.replacement)
            i_base = md_edit.end
            i_md += 1
            continue
        if tex_here:
            if md_edit and _overlaps(tex_edit, md_edit):
                conflicts.append(f"overlap at base index {i_base}")
                i_base = max(tex_edit.end, md_edit.end)
                i_md += 1
                i_tex += 1
                continue
            merged.extend(tex_edit.replacement)
            i_base = tex_edit.end
            i_tex += 1
            continue
        if i_base >= len(base):
            break
    return MergeResult(merged, conflicts)


def _edits_identical(left: Edit, right: Edit) -> bool:
    """Return True if two edits target the same range and content."""
    return left.start == right.start and left.end == right.end and left.replacement == right.replacement


def _overlaps(left: Edit, right: Edit) -> bool:
    """Return True if two edits touch overlapping base ranges.
    Inserts are treated as zero-width ranges that can still collide.
    """
    if left.start == left.end and right.start == right.end:
        return left.start == right.start
    if left.start == left.end:
        return right.start <= left.start < right.end
    if right.start == right.end:
        return left.start <= right.start < left.end
    return left.start < right.end and right.start < left.end


def _state_from_items(items: list[str]) -> SectionState:
    """Build a new state snapshot from merged items.
    The base list is updated and hashes are refreshed for both sides.
    """
    return SectionState(
        base_items=list(items),
        md_hash=_hash_items(items),
        tex_hash=_hash_items(items),
        md_count=len(items),
        tex_count=len(items),
    )


def _can_update_md(
    doc: MdDocument,
    section: SectionKey,
    new_items: list[str],
    warnings: list[str],
) -> bool:
    """Return True if markdown can be updated for a section.
    Requires either existing groups or a known section heading.
    """
    if section in doc.items_by_section:
        return True
    if not new_items:
        return True
    if section in doc.heading_line_by_section:
        return True
    warnings.append(f"No markdown heading found for section {section}")
    return False


def _can_update_tex(
    docs: dict[str, TexDocument],
    section: SectionKey,
    new_items: list[str],
    warnings: list[str],
) -> bool:
    """Return True if latex can be updated for a section.
    Requires either existing blocks or a known section header index.
    """
    top = section[0] if section else ""
    doc = docs.get(top)
    if not doc:
        warnings.append(f"No latex file found for section {section}")
        return False
    if section in doc.sync_blocks_by_section:
        return True
    if not new_items:
        return True
    if section in doc.section_insert_index:
        return True
    warnings.append(f"No latex section header found for section {section}")
    return False


def _apply_tex_updates(
    docs: dict[str, TexDocument],
    updates: dict[SectionKey, list[str]],
    warnings: list[str],
) -> list[Path]:
    """Apply updates to latex files and write changes.
    Each top-level section file is updated independently.
    Warnings are collected for any file write failures.
    """
    updated: list[Path] = []
    updates_by_doc: dict[str, dict[SectionKey, list[str]]] = {}
    for section, items in updates.items():
        top = section[0] if section else ""
        if not top:
            continue
        updates_by_doc.setdefault(top, {})[section] = items

    for top, section_updates in updates_by_doc.items():
        doc = docs.get(top)
        if not doc:
            continue
        new_lines, tex_warnings = apply_tex_updates(doc, section_updates)
        warnings.extend(tex_warnings)
        new_text = "".join(new_lines)
        original_text = "".join(_render_doc(doc))
        if new_text != original_text:
            try:
                doc.path.parent.mkdir(parents=True, exist_ok=True)
                doc.path.write_text(new_text, encoding="utf-8")
                updated.append(doc.path)
            except OSError as exc:
                warnings.append(f"Failed to write latex: {exc}")
    return updated


def _render_doc(doc: TexDocument) -> list[str]:
    """Rebuild the original latex lines from parsed blocks."""
    lines: list[str] = []
    for block in doc.blocks:
        if isinstance(block, (StaticBlock, SyncBlock)):
            lines.extend(block.lines)
    return lines
