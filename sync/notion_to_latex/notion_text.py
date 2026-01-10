

from enum import Enum, auto 
from dataclasses import dataclass
from typing import Any, Dict

NotionBlock = Dict[str, Any]

class NotionTextType(Enum):
    """Notion text type remapped to latex formatting
    """
    heading_1 = "section"
    heading_2 = "subsection"
    heading_3 = "heading_3"
    bulleted_list = "paragraph"
    paragraph = "raw_text"
    numbered_list = "numbered_list"
    latex_inline = "latex_inline"
    equation = "equation"
    code = "code"


@dataclass
class NotionContent:
    texttype: NotionTextType
    text: str

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        pass

@dataclass
class TextSection(NotionContent):
    texttype: NotionTextType = NotionTextType.heading_1
    text: str = ""

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("heading_1", {}).get("rich_text", {})
        if len(rich_text) == 0:
            return ""
        return rich_text[0].get("text", "").get("content", "").strip()

@dataclass
class TextSubsection(NotionContent):
    texttype: NotionTextType = NotionTextType.heading_2
    text: str = ""

    @staticmethod
    def skip_block(raw_block: NotionBlock) -> bool:
        rich_text = raw_block.get("heading_2", {}).get("rich_text", {})
        parts = []
        for text in rich_text:
            if text['annotations'].get('strikethrough'):
                skip = True # Skip text with strikethrough
            else:
                skip = False
            parts.append(skip)
        return all(parts)

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("heading_2", {}).get("rich_text", {})
        if len(rich_text) == 0:
            return ""
        return rich_text[0].get("text", "").get("content", "").strip()

@dataclass
class TextHeading3(NotionContent):
    texttype: NotionTextType = NotionTextType.heading_3
    text: str = ""

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("heading_3", {}).get("rich_text", {})
        if len(rich_text) == 0:
            return ""
        return rich_text[0].get("text", "").get("content", "").strip()

@dataclass
class TextParagraph(NotionContent):
    texttype: NotionTextType = NotionTextType.bulleted_list
    text: str = ""

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("bulleted_list_item", {}).get("rich_text", {})
        if len(rich_text) == 0:
            return ""
        # return rich_text[0].get("text", "").get("content", "").strip()
        parts = []
        for text in rich_text:
            content = text['text']['content']
            if text['annotations'].get('strikethrough'):
                continue  # Skip text with strikethrough
            if text['annotations']['bold']:
                content = f"\\textbf{{{content}}}"
            if text['annotations']['italic']:
                content = f"\\textit{{{content}}}"
            parts.append(content)
        return ''.join(parts).strip()

@dataclass
class TextRaw(NotionContent):
    texttype: NotionTextType = NotionTextType.paragraph
    text: str = ""

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("paragraph", {}).get("rich_text", {})
        if len(rich_text) == 0:
            return ""
        return rich_text[0].get("text", "").get("content", "").strip()

@dataclass
class TextNumbered(NotionContent):
    texttype: NotionTextType = NotionTextType.numbered_list
    text: str = ""

    # @staticmethod
    # def parse_block(raw_block: NotionBlock) -> str:
    #     rich_text = raw_block.get("numbered_list_item", {}).get("rich_text", {})
    #     if len(rich_text) == 0:
    #         return ""
    #     return rich_text[0].get("text", "").get("content", "")

def _remove_latex_tags(text: str) -> str:
    return text.replace("<latex_inline>", "").replace("</latex_inline>", "")

@dataclass
class TextLatex(NotionContent):
    texttype: NotionTextType = NotionTextType.latex_inline
    text: str = ""

    @staticmethod
    def is_latex_block(block: NotionBlock) -> bool:
        text = TextRaw.parse_block(block)
        return text.strip().startswith("<latex_inline>")

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("paragraph", {}).get("rich_text", {})
        # clumsy workaround to skip strikethrough latex inlines
        for text in rich_text:
            if text['annotations'].get('strikethrough'):
                return ""
        if len(rich_text) == 0:
            return ""
        return _remove_latex_tags(rich_text[0].get("text", "").get("content", "").strip())

@dataclass
class TextEquation(NotionContent):
    texttype: NotionTextType = NotionTextType.equation
    text: str = ""

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("equation", {}).get("expression", {})
        return rich_text

@dataclass
class TextCode(NotionContent):
    texttype: NotionTextType = NotionTextType.code
    text: str = ""

    @staticmethod
    def parse_block(raw_block: NotionBlock) -> str:
        rich_text = raw_block.get("code", {}).get("rich_text", {})
        if rich_text:
            code_text = '\n'.join([text['text']['content'] for text in rich_text])
            return code_text
        else:
            return ""


