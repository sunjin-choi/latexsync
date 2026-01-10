
import os
from pathlib import Path
import requests
from notion_client import Client as NotionClient

from sync.notion_text import (
    TextSection,
    TextSubsection,
    TextHeading3,
    TextParagraph,
    TextNumbered,
    TextLatex,
    TextEquation,
    TextCode,
)

# # Initialize the Notion client
# notion = Client(auth=os.getenv("NOTION_API_KEY"))

def convert_to_uuid(raw_id):
    """
    Convert a raw Notion ID to a UUID format.
    
    Parameters:
    raw_id (str): The raw Notion ID (32-character string without dashes).
    
    Returns:
    str: The Notion ID in UUID format (with dashes).
    """
    if len(raw_id) != 32:
        raise ValueError("The raw_id must be a 32-character string.")
    
    return f"{raw_id[:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"


def extract_uuid_from_full_id(full_id, page_name):
    """
    Extracts the UUID from a full Notion page ID given the known page name.
    
    Parameters:
    full_id (str): The full Notion page ID.
    page_name (str): The known page name.
    
    Returns:
    str: The UUID extracted from the full ID.
    """
    try:
        # Find the position of the page name
        page_name_position = full_id.index(page_name)
        # Extract the part that comes after the page name
        raw_id = full_id[page_name_position + len(page_name) + 1:]
        # Convert to UUID format
        return convert_to_uuid(raw_id)
    except ValueError:
        raise ValueError("The page name was not found in the full ID.")


# # Function to fetch data from a Notion page
# def fetch_notion_page(page_id):
#     query = {
#         "filter": {
#             "or": [
#                 {
#                     "property": "Status",
#                     "select": {
#                         "equals": "To Do"
#                     }
#                 }
#             ]
#         }
#     }
#     response = notion.pages.query(page_id=page_id, **query)
#     return response

def sanity_check_page_connection(notion_client: NotionClient, page_id):
    """
    Performs a sanity check by fetching properties of a Notion page.
    
    Parameters:
    page_id (str): The UUID of the Notion page.
    
    Returns:
    dict: The properties of the Notion page if the connection is successful.
    """
    try:
        response = notion_client.pages.retrieve(page_id=page_id)
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# def retrieve_page_content(notion_client: NotionClient, page_id):
#     """
#     Retrieves and prints the content of a Notion page.
#
#     Parameters:
#     page_id (str): The UUID of the Notion page.
#
#     Returns:
#     list: A list of blocks representing the page content.
#     """
#     try:
#         blocks = notion_client.blocks.children.list(block_id=page_id)
#         return blocks['results']
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         return None
#

def retrieve_page_content(notion_client: NotionClient, page_id):
    """
    Retrieves the content of a Notion page using pagination.
    
    Parameters:
    page_id (str): The UUID of the Notion page.
    
    Returns:
    list: A list of blocks representing the page content.
    """
    all_blocks = []
    next_cursor = None
    has_more = True

    while has_more:
        try:
            response = notion_client.blocks.children.list(block_id=page_id, start_cursor=next_cursor)
            blocks = response['results']
            all_blocks.extend(blocks)
            next_cursor = response.get('next_cursor')
            has_more = response.get('has_more', False)
        except Exception as e:
            print(f"An error occurred: {e}")
            break

    return all_blocks

def read_page_content(notion_client: NotionClient, blocks, indent=0):
    """
    Yields the content of the page blocks one by one as NotionContent instances.
    
    Parameters:
    blocks (list): A list of blocks representing the page content.
    indent (int): The current indentation level.
    
    Yields:
    NotionContent: An instance of NotionContent or its subclasses representing the block content.
    """
    paragraph_buffer = []

    def flush_paragraphs():
        if paragraph_buffer:
            combined_text = '\n'.join(paragraph_buffer)
            paragraph_buffer.clear()
            return TextParagraph(text=combined_text)
        return None

    for block in blocks:
        block_type = block['type']
        content = None

        if block_type == 'bulleted_list_item':
            text = TextParagraph.parse_block(block)
            if text:
                paragraph_buffer.append(' ' * indent + text)

            # Check if there are nested children
            if block['has_children']:
                child_blocks = notion_client.blocks.children.list(block_id=block['id'])['results']
                for child_content in read_page_content(notion_client, child_blocks, indent):
                    paragraph_buffer.append(child_content.text)

        elif block_type in ['heading_1', 'heading_2', 'heading_3', 'numbered_list_item']:
            if paragraph_buffer:
                flushed_content = flush_paragraphs()
                if flushed_content:
                    yield flushed_content

            if block_type == 'heading_1':
                content = TextSection(text=TextSection.parse_block(block))
            elif block_type == 'heading_2':
                if TextSubsection.skip_block(block):
                    continue
                content = TextSubsection(text=TextSubsection.parse_block(block))
            elif block_type == 'heading_3':
                content = TextHeading3(text=TextHeading3.parse_block(block))
            elif block_type == 'numbered_list_item':
                content = TextNumbered(text=' ' * indent + TextNumbered.parse_block(block))
                if block['has_children']:
                    child_blocks = notion_client.blocks.children.list(block_id=block['id'])['results']
                    for child_content in read_page_content(notion_client, child_blocks, indent):
                        paragraph_buffer.append(child_content.text)

        elif block_type == 'paragraph':
            # Currently assuming a bare text would always start a new paragraph
            if paragraph_buffer:
                flushed_content = flush_paragraphs()
                if flushed_content:
                    yield flushed_content

            is_latex = TextLatex.is_latex_block(block)
            if is_latex:
                content = TextLatex(text=TextLatex.parse_block(block))
            else:
                text = TextParagraph.parse_block(block)
                if text:
                    paragraph_buffer.append(' ' * indent + text)

        elif block_type == 'equation':
            # Currently assuming a bare equation would always start a new paragraph
            if paragraph_buffer:
                flushed_content = flush_paragraphs()
                if flushed_content:
                    yield flushed_content
            content = TextEquation(text=block['equation']['expression'])

        elif block_type == 'code':
            # Currently assuming a bare code block would always start a new paragraph
            if paragraph_buffer:
                flushed_content = flush_paragraphs()
                if flushed_content:
                    yield flushed_content
            code_text = '\n'.join([rich_text['text']['content'] for rich_text in block['code']['rich_text']])
            content = TextCode(text=code_text)

        if content:
            yield content

    # Flush remaining paragraphs at the end
    if paragraph_buffer:
        flushed_content = flush_paragraphs()
        if flushed_content:
            yield flushed_content

# # Example function to process the content
# def process_page_content(blocks):
#     """
#     Processes the content of the page blocks.
#
#     Parameters:
#     blocks (list): A list of blocks representing the page content.
#
#     Returns:
#     list: A list of NotionContent instances.
#     """
#     content_list = []
#     for content in read_page_content(blocks):
#         content_list.append(content)
#     return content_list

# Updated process_page_content function
def process_page_content(notion_client, blocks, build_dir, heading_to_section):
    """
    Processes the content of the page blocks and writes to LaTeX files.
    
    Parameters:
    blocks (list): A list of blocks representing the page content.
    """
    current_section = None
    section_content = []

    for content in read_page_content(notion_client, blocks):
        if isinstance(content, TextSection):
            if current_section:
                write_latex_file(current_section, section_content, build_dir, heading_to_section)
            current_section = content.text
            if current_section.lower() == "abstract":
                section_content = [""]
            else:
                section_content = [f"\\section{{{content.text}}}\n"]

            print(f"Processing section: {content.text}")

        elif isinstance(content, TextSubsection):
            section_content.append(f"\\subsection{{{content.text}}}\n")
        elif isinstance(content, TextParagraph):
            paragraph_text = content.text.replace('\n', '\n')
            section_content.append(f"{paragraph_text}\n\n")
        elif isinstance(content, TextLatex):
            section_content.append(f"{content.text}\n")

        elif isinstance(content, TextEquation):
            section_content.append(f"\\[ {content.text} \\]")
        elif isinstance(content, TextCode):
            # section_content.append(f"\\begin{{verbatim}}\n{content.text}\n\\end{{verbatim}}")
            section_content.append(f"\\begin{{lstlisting}}\n{content.text}\n\\end{{lstlisting}}")

    if current_section:
        write_latex_file(current_section, section_content, build_dir, heading_to_section)
    
    return section_content


def _remove_first_empty_lines(content):
    """
    Removes the first empty lines from the content.
    
    Parameters:
    content (list): The content to be processed.
    
    Returns:
    list: The content with the first empty lines removed.
    """
    for i, line in enumerate(content):
        if line.strip() is "":
            continue
        else:
            return content[i:]
    return []

def write_latex_file(section_title, content, build_dir, heading_to_section):
    """
    Writes the content to a LaTeX file named after the section title.
    
    Parameters:
    section_title (str): The title of the section, used as the filename.
    content (list): The content of the section to be written to the file.
    """
    # filename = f"{section_title.replace(' ', '_')}.tex"
    fname = heading_to_section.get(section_title, "")
    if fname == "":
        print(f"Section {section_title} not found in heading_to_section")
        return
    filename = f"{fname}.tex"
    filepath = Path(build_dir) / filename
    if not filepath.parent.exists():
        filepath.parent.mkdir(parents=True)

    with open(filepath, 'w') as f:
        f.write('\n'.join(_remove_first_empty_lines(content)))
        # f.write('\n'.join(content))
        print(f"File written: {section_title} to {filepath}")



