"""Markdown parser/updater that groups bullets for syncing.
This module extracts heading-scoped bullet groups as sync items.
Only contiguous top-level bullets are considered for sync.
Updates are applied by replacing or inserting bullet groups in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .ir import SectionKey


@dataclass
class MdGroup:
    """Contiguous bullet group treated as one sync unit."""
    section: SectionKey
    start_line: int
    end_line: int
    prefix: str
    items: list[str]


@dataclass
class MdDocument:
    """Parsed markdown document with section-group mapping."""
    path: Path
    lines: list[str]
    items_by_section: dict[SectionKey, list[MdGroup]]
    raw_items_by_section: dict[SectionKey, list[str]]
    heading_line_by_section: dict[SectionKey, int]
    warnings: list[str]


def parse_markdown(path: Path) -> MdDocument:
    """Parse a markdown file into heading-scoped bullet groups.
    Headings build a section path that scopes subsequent bullets.
    Contiguous top-level bullets are grouped into a single sync unit.
    Blank lines or non-bullet lines terminate the current group.
    Non-list content is preserved in lines but ignored for syncing.
    """
    warnings: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as exc:
        return MdDocument(path, [], {}, {}, {}, [f"Failed to read markdown: {exc}"])

    heading_re = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
    list_re = re.compile(r"^([\t ]*)([-*+])\s+(.+?)\s*$")

    current: list[str] = []
    items_by_section: dict[SectionKey, list[MdGroup]] = {}
    raw_items_by_section: dict[SectionKey, list[str]] = {}
    heading_line_by_section: dict[SectionKey, int] = {}
    group_items: list[str] = []
    group_start: int | None = None
    group_prefix = ""
    group_section: SectionKey | None = None

    def flush_group() -> None:
        """Finalize and store the current bullet group."""
        nonlocal group_items, group_start, group_prefix, group_section
        if not group_items or group_start is None or group_section is None:
            group_items = []
            group_start = None
            group_prefix = ""
            group_section = None
            return
        end_line = group_start + len(group_items) - 1
        group = MdGroup(
            section=group_section,
            start_line=group_start,
            end_line=end_line,
            prefix=group_prefix,
            items=list(group_items),
        )
        items_by_section.setdefault(group_section, []).append(group)
        raw_items_by_section.setdefault(group_section, []).append("\n".join(group_items))
        group_items = []
        group_start = None
        group_prefix = ""
        group_section = None

    for idx, line in enumerate(lines):
        heading_match = heading_re.match(line.rstrip("\n"))
        if heading_match:
            flush_group()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if level == 1:
                current = [title]
            elif level == 2:
                current = [current[0], title] if current else [title]
            elif level == 3:
                if not current:
                    current = [title]
                else:
                    base = current[0]
                    sub = current[1] if len(current) > 1 else ""
                    current = [base] + ([sub] if sub else []) + [title]
            if current:
                heading_line_by_section[tuple(current)] = idx
            continue

        list_match = list_re.match(line.rstrip("\n"))
        if not list_match:
            flush_group()
            continue
        indent = list_match.group(1)
        if indent != "":
            flush_group()
            continue
        if not current:
            warnings.append(f"List item without heading at line {idx + 1}")
            continue
        raw_text = list_match.group(3).strip()
        prefix = f"{indent}{list_match.group(2)} "
        section = tuple(current)
        if group_section != section or group_start is None:
            flush_group()
            group_section = section
            group_start = idx
            group_prefix = prefix
        group_items.append(raw_text)

    flush_group()

    return MdDocument(path, lines, items_by_section, raw_items_by_section, heading_line_by_section, warnings)


def apply_markdown_updates(
    doc: MdDocument,
    updates: dict[SectionKey, list[str]],
) -> tuple[list[str], list[str]]:
    """Apply group-level updates to markdown lines.
    Existing bullet groups are replaced in place using line ranges.
    New groups are inserted after the last group or after the heading.
    Extra groups are removed by deleting their original line ranges.
    The function returns updated lines plus warnings for missing sections.
    """
    warnings: list[str] = []
    lines = list(doc.lines)
    operations: list[tuple[int, int, list[str]]] = []
    for section, new_items in updates.items():
        old_groups = doc.items_by_section.get(section, [])
        common = min(len(old_groups), len(new_items))
        for group, new_text in zip(old_groups[:common], new_items[:common]):
            replacement = _render_group_lines(new_text, group.prefix)
            operations.append((group.start_line, group.end_line, replacement))
        if len(new_items) > len(old_groups):
            extra = new_items[len(old_groups):]
            insert_at, prefix, needs_blank = _md_insertion_point(lines, doc, section, old_groups)
            if insert_at is None:
                warnings.append(f"No heading found for section {section}")
                continue
            insert_lines = _render_group_block(extra, prefix, needs_blank)
            operations.append((insert_at, insert_at - 1, insert_lines))
        elif len(new_items) < len(old_groups):
            for group in old_groups[len(new_items):]:
                operations.append((group.start_line, group.end_line, []))

    for start, end, replacement in sorted(operations, key=lambda op: (-op[0], -op[1])):
        if end < start:
            if replacement:
                lines[start:start] = replacement
        else:
            lines[start : end + 1] = replacement
    return lines, warnings


def _md_insertion_point(
    lines: list[str],
    doc: MdDocument,
    section: SectionKey,
    old_groups: list[MdGroup],
) -> tuple[int | None, str, bool]:
    """Find the insertion point for new bullet groups in a section.
    If groups exist, insert after the last group (optionally after a blank).
    If no groups exist, insert after the heading line and its blank padding.
    Returns the insertion index, preferred bullet prefix, and blank flag.
    """
    if old_groups:
        last_group = old_groups[-1]
        insert_at = last_group.end_line + 1
        if insert_at < len(lines) and lines[insert_at].strip() == "":
            return insert_at + 1, last_group.prefix, False
        needs_blank = insert_at > 0 and lines[insert_at - 1].strip() != ""
        return insert_at, last_group.prefix, needs_blank
    heading_index = doc.heading_line_by_section.get(section)
    if heading_index is None:
        return None, "- ", False
    insert_at = heading_index + 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    needs_blank = insert_at > 0 and lines[insert_at - 1].strip() != ""
    return insert_at, "- ", needs_blank


def _render_group_lines(text: str, prefix: str) -> list[str]:
    """Render a single group text into bullet lines.
    Each non-empty line becomes one bullet item with the given prefix.
    Empty lines inside the group are dropped during rendering.
    """
    items = [item.strip() for item in text.splitlines() if item.strip() != ""]
    return [f"{prefix}{item}\n" for item in items]


def _render_group_block(groups: list[str], prefix: str, needs_blank: bool) -> list[str]:
    """Render multiple groups into lines, separating groups with blanks.
    A blank line can be inserted ahead of the block when needed.
    Groups are separated by a single blank line to preserve grouping.
    """
    lines: list[str] = []
    if needs_blank:
        lines.append("\n")
    for idx, group in enumerate(groups):
        if idx > 0:
            lines.append("\n")
        lines.extend(_render_group_lines(group, prefix))
    return lines
