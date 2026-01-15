"""Mapper registry that parses markdown/latex into IR and renders back.
This module defines the mapper protocols and the registry pipeline.
Parsers call into the registry to turn text into IR nodes.
Renderers call into the registry to turn IR nodes back into text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import re

from .ir import Node, Text


class InlineMapper(Protocol):
    """Mapper interface for inline markdown/latex fragments."""
    name: str
    priority: int
    node_type: type

    def match_md(self, text: str, pos: int) -> re.Match[str] | None: ...

    def match_tex(self, text: str, pos: int) -> re.Match[str] | None: ...

    def md_to_node(self, match: re.Match[str]) -> Node: ...

    def tex_to_node(self, match: re.Match[str]) -> Node: ...

    def node_to_md(self, node: Node) -> str: ...

    def node_to_tex(self, node: Node) -> str: ...


class BlockMapper(Protocol):
    """Mapper interface for block-level markdown/latex fragments."""
    name: str
    priority: int
    node_type: type

    def match_md(self, text: str) -> re.Match[str] | None: ...

    def match_tex(self, text: str) -> re.Match[str] | None: ...

    def md_to_node(self, match: re.Match[str]) -> Node: ...

    def tex_to_node(self, match: re.Match[str]) -> Node: ...

    def node_to_md(self, node: Node) -> str: ...

    def node_to_tex(self, node: Node) -> str: ...


@dataclass
class Registry:
    """Registry that parses and renders content using mappers."""
    block_mappers: list[BlockMapper]
    inline_mappers: list[InlineMapper]

    def __post_init__(self) -> None:
        """Sort mappers by priority and build a renderer lookup."""
        self.block_mappers.sort(key=lambda m: m.priority, reverse=True)
        self.inline_mappers.sort(key=lambda m: m.priority, reverse=True)
        self._renderers: dict[type, BlockMapper | InlineMapper] = {}
        for mapper in self.block_mappers + self.inline_mappers:
            self._renderers.setdefault(mapper.node_type, mapper)

    def parse_md_block(self, text: str) -> list[Node]:
        """Parse a markdown block into IR nodes."""
        for mapper in self.block_mappers:
            match = mapper.match_md(text.strip())
            if match:
                return [mapper.md_to_node(match)]
        return self._parse_inline(text, mode="md")

    def parse_tex_block(self, text: str) -> list[Node]:
        """Parse a latex block into IR nodes."""
        for mapper in self.block_mappers:
            match = mapper.match_tex(text.strip())
            if match:
                return [mapper.tex_to_node(match)]
        return self._parse_inline(text, mode="tex")

    def render_md(self, nodes: list[Node]) -> str:
        """Render IR nodes into markdown text."""
        return "".join(self._render_node_md(node) for node in nodes)

    def render_tex(self, nodes: list[Node]) -> str:
        """Render IR nodes into latex text."""
        return "".join(self._render_node_tex(node) for node in nodes)

    def _render_node_md(self, node: Node) -> str:
        """Render a single node into markdown."""
        if isinstance(node, Text):
            return node.value
        mapper = self._renderers.get(type(node))
        if not mapper:
            return ""
        return mapper.node_to_md(node)

    def _render_node_tex(self, node: Node) -> str:
        """Render a single node into latex."""
        if isinstance(node, Text):
            return node.value
        mapper = self._renderers.get(type(node))
        if not mapper:
            return ""
        return mapper.node_to_tex(node)

    def _parse_inline(self, text: str, mode: str) -> list[Node]:
        """Parse inline content into nodes using inline mappers."""
        nodes: list[Node] = []
        buf: list[str] = []
        pos = 0
        while pos < len(text):
            matched = False
            for mapper in self.inline_mappers:
                match = mapper.match_md(text, pos) if mode == "md" else mapper.match_tex(text, pos)
                if match:
                    if buf:
                        nodes.append(Text("".join(buf)))
                        buf = []
                    node = mapper.md_to_node(match) if mode == "md" else mapper.tex_to_node(match)
                    nodes.append(node)
                    pos = match.end()
                    matched = True
                    break
            if not matched:
                buf.append(text[pos])
                pos += 1
        if buf:
            nodes.append(Text("".join(buf)))
        return nodes
