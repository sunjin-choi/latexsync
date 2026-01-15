"""IR node definitions shared across parsing and rendering modules.
These dataclasses represent semantic units (text, inline math, figures).
They are produced by parsers and consumed by renderers via the registry.
Mappers convert between raw text and these nodes in both directions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass(frozen=True)
class Text:
    """Plain text node."""
    value: str


@dataclass(frozen=True)
class Strong:
    """Bold text node."""
    value: str


@dataclass(frozen=True)
class Emphasis:
    """Italic text node."""
    value: str


@dataclass(frozen=True)
class InlineCode:
    """Inline code node."""
    value: str


@dataclass(frozen=True)
class InlineMath:
    """Inline math node delimited by $...$."""
    value: str


@dataclass(frozen=True)
class Strikethrough:
    """Strikethrough node mapped to \\ignore{} in latex."""
    value: str


@dataclass(frozen=True)
class RawTex:
    """Raw LaTeX snippet passthrough node."""
    value: str


@dataclass(frozen=True)
class Figure:
    """Figure block node with optional caption and attributes."""
    path: str
    caption: str = ""
    attrs: dict[str, str] = field(default_factory=dict)


Node = Union[Text, Strong, Emphasis, InlineCode, InlineMath, Strikethrough, RawTex, Figure]
SectionKey = tuple[str, ...]
