from __future__ import annotations

import html


def is_blank(line: str) -> bool:
    return not line.strip()


def normalize_title(title: str, fallback: str) -> str:
    value = title.strip()
    return value if value else fallback


def html_escape(text: str) -> str:
    return html.escape(text, quote=False)

