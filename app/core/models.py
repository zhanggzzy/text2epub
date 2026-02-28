from dataclasses import dataclass


@dataclass
class TocItem:
    title: str
    start_line: int
    end_line: int
    level: int  # 1=卷, 2=章
    level_name: str


@dataclass
class TocGroup:
    volume_title: str | None
    chapters: list[TocItem]


@dataclass
class RuleLevel:
    name: str
    rules: list[str]


@dataclass
class EpubMetadata:
    title: str
    author: str
    page_count: int
    categories: list[str]
    cover_path: str | None = None
