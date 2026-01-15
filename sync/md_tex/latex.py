"""Latex parser/updater that manages syncable paragraph blocks.
This module scans section headers and groups syncable paragraphs.
Blocks containing unescaped comment markers are preserved as static.
Updates rewrite or insert paragraph blocks while keeping layout intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .ir import SectionKey


@dataclass
class StaticBlock:
    """Non-syncable block of latex lines."""
    lines: list[str]


@dataclass
class SyncBlock:
    """Syncable paragraph block within a section."""
    section: SectionKey
    lines: list[str]
    text: str
    indent: str
    replacement: list[str] | None = None


TexBlock = StaticBlock | SyncBlock


@dataclass
class TexDocument:
    """Parsed latex document with syncable blocks."""
    path: Path
    blocks: list[TexBlock]
    sync_blocks_by_section: dict[SectionKey, list[SyncBlock]]
    raw_text_by_section: dict[SectionKey, list[str]]
    section_insert_index: dict[SectionKey, int]
    warnings: list[str]


def parse_tex_file(path: Path, base_section: str) -> TexDocument:
    """Parse a latex file into blocks and section mappings.
    Section headers establish the current section path for sync blocks.
    Paragraph blocks without unescaped comments are treated as syncable.
    Static blocks preserve raw lines (including comment-only content).
    The result includes per-section indexes for insertion points.
    """
    warnings: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as exc:
        warnings.append(f"Failed to read latex: {exc}")
        return TexDocument(path, [], {}, {}, {}, warnings)

    blocks: list[TexBlock] = []
    sync_blocks_by_section: dict[SectionKey, list[SyncBlock]] = {}
    raw_text_by_section: dict[SectionKey, list[str]] = {}
    section_insert_index: dict[SectionKey, int] = {}

    current_section: list[str] = [base_section] if base_section else []
    if current_section:
        section_insert_index[tuple(current_section)] = 0
    buffer: list[str] = []

    def flush_buffer() -> None:
        if not buffer:
            return
        block = _make_block(buffer, tuple(current_section))
        blocks.append(block)
        if isinstance(block, SyncBlock):
            sync_blocks_by_section.setdefault(block.section, []).append(block)
            raw_text_by_section.setdefault(block.section, []).append(block.text.strip())
        buffer.clear()

    for line in lines:
        if _is_section_line(line):
            flush_buffer()
            blocks.append(StaticBlock([line]))
            section_title, level = _parse_section(line)
            current_section = _update_section_path(current_section, base_section, section_title, level)
            if current_section:
                section_insert_index[tuple(current_section)] = len(blocks)
            continue
        if _is_blank(line):
            flush_buffer()
            blocks.append(StaticBlock([line]))
            continue
        buffer.append(line)

    flush_buffer()
    return TexDocument(
        path,
        blocks,
        sync_blocks_by_section,
        raw_text_by_section,
        section_insert_index,
        warnings,
    )


def apply_tex_updates(
    doc: TexDocument,
    updates: dict[SectionKey, list[str]],
) -> tuple[list[str], list[str]]:
    """Apply section updates to syncable blocks and return new lines.
    Existing blocks are replaced in order with new paragraph content.
    New items are inserted after the last block or at a section header.
    Extra blocks are removed by replacing them with empty line lists.
    The function returns updated lines plus warnings for missing sections.
    """
    warnings: list[str] = []
    insertions: dict[int, list[str]] = {}
    for section, new_items in updates.items():
        blocks = doc.sync_blocks_by_section.get(section, [])
        if not blocks:
            if not new_items:
                continue
            insert_at = doc.section_insert_index.get(section)
            if insert_at is None:
                warnings.append(f"No section header found for section {section}")
                continue
            insertions.setdefault(insert_at, []).extend(_render_items(new_items, ""))
            continue

        common = min(len(blocks), len(new_items))
        for block, new_text in zip(blocks[:common], new_items[:common]):
            block.replacement = _render_block_lines(new_text.strip(), block.indent)
        if len(new_items) > len(blocks):
            extra = new_items[len(blocks):]
            insert_at, needs_blank = _insertion_point(doc.blocks, blocks[-1])
            insertions.setdefault(insert_at, []).extend(
                _render_items(extra, blocks[-1].indent, needs_blank)
            )
        elif len(new_items) < len(blocks):
            for block in blocks[len(new_items):]:
                block.replacement = []

    new_lines: list[str] = []
    for idx, block in enumerate(doc.blocks):
        if idx in insertions:
            new_lines.extend(insertions[idx])
        if isinstance(block, SyncBlock) and block.replacement is not None:
            new_lines.extend(block.replacement)
        elif isinstance(block, SyncBlock):
            new_lines.extend(block.lines)
        else:
            new_lines.extend(block.lines)
    if len(doc.blocks) in insertions:
        new_lines.extend(insertions[len(doc.blocks)])
    return new_lines, warnings


def _make_block(lines: list[str], section: SectionKey) -> TexBlock:
    """Create a SyncBlock or StaticBlock based on line content.
    Sync blocks are only created for comment-free paragraph lines.
    Static blocks preserve original content for non-syncable text.
    """
    if _is_syncable_block(lines):
        indent = _leading_ws(lines[0])
        stripped = [_strip_indent(line, indent).rstrip("\n") for line in lines]
        text = "\n".join(stripped)
        return SyncBlock(section=section, lines=list(lines), text=text, indent=indent)
    return StaticBlock(lines=list(lines))


def _is_syncable_block(lines: list[str]) -> bool:
    """Return True if the block contains no latex comments.
    Unescaped percent signs anywhere in the block make it non-syncable.
    Comment-only lines are treated as static to preserve annotations.
    """
    for line in lines:
        if _find_unescaped_percent(line) is not None:
            return False
        if line.lstrip().startswith("%"):
            return False
    return True


def _render_block_lines(text: str, indent: str) -> list[str]:
    """Render a paragraph text into indented latex lines.
    Each line in the paragraph is emitted with the original indent.
    Empty text yields a single blank line to preserve spacing.
    """
    if text == "":
        return ["\n"]
    lines = text.splitlines() or [""]
    return [f"{indent}{line}\n" for line in lines]


def _render_items(items: list[str], indent: str, needs_blank: bool = False) -> list[str]:
    """Render multiple paragraphs into lines with optional blank separator.
    When requested, a blank line is inserted before new paragraphs.
    Each item is rendered using the same indentation for consistency.
    """
    rendered: list[str] = []
    if needs_blank:
        rendered.append("\n")
    for item in items:
        rendered.extend(_render_block_lines(item.strip(), indent))
    return rendered


def _leading_ws(line: str) -> str:
    """Return leading whitespace from a line."""
    match = re.match(r"^[\t ]*", line)
    return match.group(0) if match else ""


def _strip_indent(line: str, indent: str) -> str:
    """Strip a fixed indent prefix from a line."""
    if line.startswith(indent):
        return line[len(indent):]
    return line.lstrip(" \t")


def _is_blank(line: str) -> bool:
    """Return True for blank lines."""
    return line.strip() == ""


def _is_section_line(line: str) -> bool:
    """Return True if the line starts a section header.
    Comment text is stripped before matching section commands.
    """
    code = _strip_comments(line)
    if code.strip() == "":
        return False
    return bool(re.match(r"^\s*\\(subsubsection|subsection|section)\*?\{", code))


def _parse_section(line: str) -> tuple[str, int]:
    """Parse a section header and return (title, level).
    Section level is mapped to 1/2/3 for section/subsection/subsubsection.
    """
    code = _strip_comments(line)
    match = re.match(r"^\s*\\(subsubsection|subsection|section)\*?\{(.+?)\}", code)
    if not match:
        return "", 1
    kind = match.group(1)
    title = match.group(2).strip()
    level = 1
    if kind == "subsection":
        level = 2
    elif kind == "subsubsection":
        level = 3
    return title, level


def _update_section_path(
    current: list[str],
    base: str,
    title: str,
    level: int,
) -> list[str]:
    """Update the current section path based on header level.
    The path is a tuple of headings used as a section key in sync maps.
    """
    if level == 1:
        return [title]
    if level == 2:
        top = current[0] if current else base
        return [top, title] if top else [title]
    top = current[0] if current else base
    sub = current[1] if len(current) > 1 else ""
    parts = [p for p in (top, sub, title) if p]
    return parts


def _find_unescaped_percent(line: str) -> int | None:
    """Find the first unescaped percent sign in a line.
    Escaped percent signs (\\%) are ignored during scanning.
    """
    i = 0
    while i < len(line):
        if line[i] == "%" and not _is_escaped(line, i):
            return i
        i += 1
    return None


def _is_escaped(line: str, idx: int) -> bool:
    """Return True if a character index is escaped with backslashes."""
    backslashes = 0
    j = idx - 1
    while j >= 0 and line[j] == "\\":
        backslashes += 1
        j -= 1
    return backslashes % 2 == 1


def _strip_comments(line: str) -> str:
    """Return the line content before the first unescaped percent.
    This is used to detect section headers without comment noise.
    """
    pos = _find_unescaped_percent(line)
    if pos is None:
        return line
    return line[:pos]


def _insertion_point(blocks: list[TexBlock], last_block: SyncBlock) -> tuple[int, bool]:
    """Find insertion index after a block and whether a blank line is needed.
    If a blank block already follows the last sync block, reuse it.
    Otherwise request a blank line to keep paragraph separation.
    """
    last_index = _last_block_index(blocks, last_block)
    insert_at = last_index + 1
    if insert_at < len(blocks) and _is_blank_block(blocks[insert_at]):
        return insert_at + 1, False
    return insert_at, True


def _last_block_index(blocks: list[TexBlock], target: SyncBlock) -> int:
    """Find the last index of a specific block object."""
    for idx in range(len(blocks) - 1, -1, -1):
        if blocks[idx] is target:
            return idx
    return len(blocks)


def _is_blank_block(block: TexBlock) -> bool:
    """Return True if a static block is entirely blank."""
    if not isinstance(block, StaticBlock):
        return False
    return all(line.strip() == "" for line in block.lines)
