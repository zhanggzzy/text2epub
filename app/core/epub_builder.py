from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ebooklib import epub

from .models import EpubMetadata, TocItem
from .utils import html_escape, normalize_title

DEFAULT_STYLE = """
body { line-height: 1.6; margin: 0 6%; }
p { text-indent: 2em; margin: 0.5em 0; }
h1 { text-align: center; margin: 1em 0; }
""".strip()


def _chapter_html(item: TocItem, lines: list[str]) -> str:
    content_lines = lines[item.start_line : item.end_line + 1]
    paragraphs = [f"<p>{html_escape(line.strip())}</p>" for line in content_lines if line.strip()]
    body = "\n".join(paragraphs) if paragraphs else "<p></p>"
    return f"<h1>{html_escape(item.title)}</h1>\n{body}"


def _build_hierarchy(items: list[TocItem]) -> list[dict]:
    roots: list[dict] = []
    stack: list[dict] = []
    for item in sorted(items, key=lambda i: (i.start_line, i.level)):
        node = {"item": item, "children": []}
        while stack and stack[-1]["item"].level >= item.level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _simple_svg_cover(title: str) -> bytes:
    safe_title = html_escape(title or "未命名作品")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600" viewBox="0 0 1200 1600">
<rect x="0" y="0" width="1200" height="1600" fill="#f5f2ea" />
<rect x="90" y="90" width="1020" height="1420" fill="#ffffff" stroke="#d7d0c2" stroke-width="6" />
<line x1="180" y1="350" x2="1020" y2="350" stroke="#99907e" stroke-width="3" />
<text x="600" y="760" text-anchor="middle" font-size="72" fill="#2b2b2b" font-family="serif">{safe_title}</text>
</svg>"""
    return svg.encode("utf-8")


def _resolve_cover_bytes(meta: EpubMetadata) -> tuple[str, bytes]:
    if meta.cover_path:
        path = Path(meta.cover_path)
        if path.exists() and path.is_file():
            ext = path.suffix.lower() or ".jpg"
            return f"cover{ext}", path.read_bytes()
    return "cover.svg", _simple_svg_cover(meta.title)


def build_epub(
    lines: list[str],
    toc_items: list[TocItem],
    output_path: str,
    metadata: EpubMetadata,
    language: str = "zh",
) -> None:
    if not lines:
        raise ValueError("文本为空，无法生成 EPUB")
    if not toc_items:
        toc_items = [TocItem(title="正文", start_line=0, end_line=len(lines) - 1, level=1, level_name="章节")]

    content_level = max(item.level for item in toc_items)
    content_items = [item for item in toc_items if item.level == content_level]

    book = epub.EpubBook()
    book.set_identifier(str(uuid4()))
    book.set_title(normalize_title(metadata.title, "未命名作品"))
    book.set_language(language)
    if metadata.author.strip():
        book.add_author(metadata.author.strip())

    for category in metadata.categories:
        if category.strip():
            book.add_metadata("DC", "subject", category.strip())
    book.add_metadata(None, "meta", "", {"name": "calculated_pages", "content": str(metadata.page_count)})

    css_item = epub.EpubItem(
        uid="style_main",
        file_name="style/main.css",
        media_type="text/css",
        content=DEFAULT_STYLE,
    )
    book.add_item(css_item)

    cover_name, cover_bytes = _resolve_cover_bytes(metadata)
    book.set_cover(cover_name, cover_bytes)

    chapter_docs: list[epub.EpubHtml] = []
    doc_map: dict[tuple[int, int, str], epub.EpubHtml] = {}
    for idx, item in enumerate(content_items, start=1):
        doc = epub.EpubHtml(
            title=item.title,
            file_name=f"chapters/chapter_{idx:03d}.xhtml",
            lang=language,
        )
        doc.content = _chapter_html(item, lines)
        doc.add_item(css_item)
        book.add_item(doc)
        chapter_docs.append(doc)
        doc_map[(item.start_line, item.level, item.title)] = doc

    hierarchy = _build_hierarchy(toc_items)

    def to_toc_entries(node: dict) -> list:
        item: TocItem = node["item"]
        children = node["children"]
        key = (item.start_line, item.level, item.title)
        if item.level == content_level and key in doc_map:
            return [doc_map[key]]

        child_entries: list = []
        for child in children:
            child_entries.extend(to_toc_entries(child))
        if not child_entries:
            return []
        return [(epub.Section(item.title), tuple(child_entries))]

    toc_entries: list = []
    for root in hierarchy:
        toc_entries.extend(to_toc_entries(root))
    if not toc_entries:
        toc_entries = chapter_docs[:]

    book.toc = tuple(toc_entries)
    book.spine = ["nav", *chapter_docs]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output), book, {})

