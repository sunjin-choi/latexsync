"""Default mapper implementations used by the registry.
These map inline and block patterns between Markdown and LaTeX.
Figure mapping is configurable and is injected at registry build time.
Add new mappers here to extend the sync surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import FigureMapping
from .ir import Emphasis, Figure, InlineCode, InlineMath, RawTex, Strong, Strikethrough
from .registry import BlockMapper, InlineMapper, Registry


class StrongMapper:
    """Mapper for bold text."""
    name = "strong"
    priority = 90
    node_type = Strong
    _md = re.compile(r"\*\*(.+?)\*\*")
    _tex = re.compile(r"\\textbf\{(.+?)\}")

    def match_md(self, text: str, pos: int) -> re.Match[str] | None:
        """Match markdown bold at the given position."""
        return self._md.match(text, pos)

    def match_tex(self, text: str, pos: int) -> re.Match[str] | None:
        """Match latex bold at the given position."""
        return self._tex.match(text, pos)

    def md_to_node(self, match: re.Match[str]) -> Strong:
        """Convert a markdown match to a Strong node."""
        return Strong(match.group(1))

    def tex_to_node(self, match: re.Match[str]) -> Strong:
        """Convert a latex match to a Strong node."""
        return Strong(match.group(1))

    def node_to_md(self, node: Strong) -> str:
        """Render a Strong node to markdown."""
        return f"**{node.value}**"

    def node_to_tex(self, node: Strong) -> str:
        """Render a Strong node to latex."""
        return f"\\textbf{{{node.value}}}"


class EmphasisMapper:
    """Mapper for italic text."""
    name = "emphasis"
    priority = 80
    node_type = Emphasis
    _md = re.compile(r"\*(.+?)\*")
    _tex = re.compile(r"\\textit\{(.+?)\}")

    def match_md(self, text: str, pos: int) -> re.Match[str] | None:
        """Match markdown italics at the given position."""
        return self._md.match(text, pos)

    def match_tex(self, text: str, pos: int) -> re.Match[str] | None:
        """Match latex italics at the given position."""
        return self._tex.match(text, pos)

    def md_to_node(self, match: re.Match[str]) -> Emphasis:
        """Convert a markdown match to an Emphasis node."""
        return Emphasis(match.group(1))

    def tex_to_node(self, match: re.Match[str]) -> Emphasis:
        """Convert a latex match to an Emphasis node."""
        return Emphasis(match.group(1))

    def node_to_md(self, node: Emphasis) -> str:
        """Render an Emphasis node to markdown."""
        return f"*{node.value}*"

    def node_to_tex(self, node: Emphasis) -> str:
        """Render an Emphasis node to latex."""
        return f"\\textit{{{node.value}}}"


class InlineCodeMapper:
    """Mapper for inline code."""
    name = "inline_code"
    priority = 70
    node_type = InlineCode
    _md = re.compile(r"`([^`]+?)`")
    _tex = re.compile(r"\\texttt\{(.+?)\}")

    def match_md(self, text: str, pos: int) -> re.Match[str] | None:
        """Match inline code in markdown at the given position."""
        return self._md.match(text, pos)

    def match_tex(self, text: str, pos: int) -> re.Match[str] | None:
        """Match inline code in latex at the given position."""
        return self._tex.match(text, pos)

    def md_to_node(self, match: re.Match[str]) -> InlineCode:
        """Convert a markdown match to an InlineCode node."""
        return InlineCode(match.group(1))

    def tex_to_node(self, match: re.Match[str]) -> InlineCode:
        """Convert a latex match to an InlineCode node."""
        return InlineCode(match.group(1))

    def node_to_md(self, node: InlineCode) -> str:
        """Render an InlineCode node to markdown."""
        return f"`{node.value}`"

    def node_to_tex(self, node: InlineCode) -> str:
        """Render an InlineCode node to latex."""
        return f"\\texttt{{{node.value}}}"


class InlineMathMapper:
    """Mapper for inline math ($...$)."""
    name = "inline_math"
    priority = 60
    node_type = InlineMath
    _md = re.compile(r"\$(.+?)\$")
    _tex = re.compile(r"\$(.+?)\$")

    def match_md(self, text: str, pos: int) -> re.Match[str] | None:
        """Match inline math in markdown at the given position."""
        if text.startswith("$$", pos):
            return None
        return self._md.match(text, pos)

    def match_tex(self, text: str, pos: int) -> re.Match[str] | None:
        """Match inline math in latex at the given position."""
        if text.startswith("$$", pos):
            return None
        return self._tex.match(text, pos)

    def md_to_node(self, match: re.Match[str]) -> InlineMath:
        """Convert a markdown match to an InlineMath node."""
        return InlineMath(match.group(1))

    def tex_to_node(self, match: re.Match[str]) -> InlineMath:
        """Convert a latex match to an InlineMath node."""
        return InlineMath(match.group(1))

    def node_to_md(self, node: InlineMath) -> str:
        """Render an InlineMath node to markdown."""
        return f"${node.value}$"

    def node_to_tex(self, node: InlineMath) -> str:
        """Render an InlineMath node to latex."""
        return f"${node.value}$"


class StrikethroughMapper:
    """Mapper for markdown strikethrough and latex \\ignore{}."""
    name = "strikethrough"
    priority = 55
    node_type = Strikethrough
    _md = re.compile(r"~~(.+?)~~")
    _tex = re.compile(r"\\\\ignore\\{(.+?)\\}")

    def match_md(self, text: str, pos: int) -> re.Match[str] | None:
        """Match markdown strikethrough at the given position."""
        return self._md.match(text, pos)

    def match_tex(self, text: str, pos: int) -> re.Match[str] | None:
        """Match latex \\ignore at the given position."""
        return self._tex.match(text, pos)

    def md_to_node(self, match: re.Match[str]) -> Strikethrough:
        """Convert a markdown match to a Strikethrough node."""
        return Strikethrough(match.group(1))

    def tex_to_node(self, match: re.Match[str]) -> Strikethrough:
        """Convert a latex match to a Strikethrough node."""
        return Strikethrough(match.group(1))

    def node_to_md(self, node: Strikethrough) -> str:
        """Render a Strikethrough node to markdown."""
        return f"~~{node.value}~~"

    def node_to_tex(self, node: Strikethrough) -> str:
        """Render a Strikethrough node to latex."""
        return f"\\\\ignore{{{node.value}}}"

class RawTexMapper:
    """Mapper for raw latex commands embedded in text."""
    name = "raw_tex"
    priority = 10
    node_type = RawTex
    _pattern = re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*")

    def match_md(self, text: str, pos: int) -> re.Match[str] | None:
        """Match raw latex in markdown at the given position."""
        return self._pattern.match(text, pos)

    def match_tex(self, text: str, pos: int) -> re.Match[str] | None:
        """Match raw latex in latex at the given position."""
        return self._pattern.match(text, pos)

    def md_to_node(self, match: re.Match[str]) -> RawTex:
        """Convert a markdown match to a RawTex node."""
        return RawTex(match.group(0))

    def tex_to_node(self, match: re.Match[str]) -> RawTex:
        """Convert a latex match to a RawTex node."""
        return RawTex(match.group(0))

    def node_to_md(self, node: RawTex) -> str:
        """Render a RawTex node to markdown."""
        return node.value

    def node_to_tex(self, node: RawTex) -> str:
        """Render a RawTex node to latex."""
        return node.value


@dataclass
class FigureMapper:
    """Mapper for figure blocks using configurable patterns."""
    mapping: FigureMapping
    name: str = "figure"
    priority: int = 100
    node_type: type = Figure

    def __post_init__(self) -> None:
        """Compile regex patterns for markdown and latex figures."""
        self._md = re.compile(self.mapping.md_pattern)
        self._tex = re.compile(self.mapping.tex_pattern, re.DOTALL)

    def match_md(self, text: str) -> re.Match[str] | None:
        """Match a markdown figure block."""
        return self._md.fullmatch(text.strip())

    def match_tex(self, text: str) -> re.Match[str] | None:
        """Match a latex figure block."""
        return self._tex.fullmatch(text.strip())

    def md_to_node(self, match: re.Match[str]) -> Figure:
        """Convert a markdown match to a Figure node."""
        path, caption = _extract_groups(match)
        return Figure(path=path, caption=caption)

    def tex_to_node(self, match: re.Match[str]) -> Figure:
        """Convert a latex match to a Figure node."""
        path, caption = _extract_groups(match)
        return Figure(path=path, caption=caption)

    def node_to_md(self, node: Figure) -> str:
        """Render a Figure node to markdown."""
        template = self.mapping.md_template
        if not node.caption:
            template = template.replace("|{caption}", "")
        return template.format(path=node.path, caption=node.caption)

    def node_to_tex(self, node: Figure) -> str:
        """Render a Figure node to latex."""
        template = self.mapping.tex_template
        if not node.caption:
            template = "\n".join(line for line in template.splitlines() if "{caption}" not in line)
        return template.format(path=node.path, caption=node.caption)


def build_registry(mapping: FigureMapping) -> Registry:
    """Build a registry with default mappers and figure mapping."""
    block_mappers: list[BlockMapper] = [FigureMapper(mapping=mapping)]
    inline_mappers: list[InlineMapper] = [
        StrongMapper(),
        EmphasisMapper(),
        InlineCodeMapper(),
        InlineMathMapper(),
        StrikethroughMapper(),
        RawTexMapper(),
    ]
    return Registry(block_mappers=block_mappers, inline_mappers=inline_mappers)


def _extract_groups(match: re.Match[str]) -> tuple[str, str]:
    """Extract path and caption from a regex match."""
    groups = match.groupdict()
    path = groups.get("path")
    caption = groups.get("caption") or ""
    if path is None:
        path = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
    if not caption and match.lastindex and match.lastindex >= 2:
        caption = match.group(2) or ""
    return path, caption
