from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .models import RuleLevel, TocGroup, TocItem
from .utils import normalize_title


@dataclass
class CompiledRule:
    regex: re.Pattern[str]
    replacement: str
    raw_rule: str


@dataclass
class MatchResult:
    level_no: int
    level_name: str
    rule: CompiledRule
    matched_text: str
    rendered_title: str


@dataclass
class CompiledLevel:
    level_no: int
    level_name: str
    rules: list[CompiledRule]


@dataclass
class LineCheckResult:
    matched: MatchResult | None
    accepted: bool
    reason: str


def default_rule_levels() -> list[RuleLevel]:
    return [
        RuleLevel(
            name="卷",
            rules=[
                r"^第([零〇一二三四五六七八九十百千万两0-9]+)卷[\s:：-]*(.*)$ => 第\1卷 \2",
                r"^卷([零〇一二三四五六七八九十百千万两0-9]+)[\s:：-]*(.*)$ => 第\1卷 \2",
                r"^(?:VOL|Volume)\s+(\d+)[\s:：-]*(.*)$ => 第\1卷 \2",
            ],
        ),
        RuleLevel(
            name="章",
            rules=[
                r"^第([零〇一二三四五六七八九十百千万两0-9]+)章[\s:：-]*(.*)$ => 第\1章 \2",
                r"^第([零〇一二三四五六七八九十百千万两0-9]+)节[\s:：-]*(.*)$ => 第\1节 \2",
                r"^([零〇一二三四五六七八九十百千万两]+)、\s*(.*)$ => 第\1章 \2",
                r"^(?:Chapter|CHAPTER)\s+([IVXLCDM\d]+)[\s:：-]*(.*)$ => Chapter \1 \2",
            ],
        ),
    ]


def _split_rule_line(rule_line: str) -> tuple[str, str]:
    text = rule_line.strip()
    if not text:
        raise ValueError("规则为空")
    if "=>" in text:
        left, right = text.split("=>", 1)
        return left.strip(), right.strip()
    return text, r"\g<0>"


def _normalize_replacement(value: str) -> str:
    if not value:
        return r"\g<0>"
    return value


def _compile_rule(rule_line: str) -> CompiledRule:
    pattern, replacement = _split_rule_line(rule_line)
    regex = re.compile(pattern)
    return CompiledRule(regex=regex, replacement=_normalize_replacement(replacement), raw_rule=rule_line)


def compile_rule_levels(rule_levels: Iterable[RuleLevel]) -> list[CompiledLevel]:
    compiled: list[CompiledLevel] = []
    for index, level in enumerate(rule_levels, start=1):
        level_name = normalize_title(level.name, f"L{index}")
        rules: list[CompiledRule] = []
        for line in level.rules:
            line = line.strip()
            if not line:
                continue
            rules.append(_compile_rule(line))
        if rules:
            compiled.append(CompiledLevel(level_no=index, level_name=level_name, rules=rules))
    return compiled


def detect_heading_level(line: str, compiled_levels: list[CompiledLevel]) -> MatchResult | None:
    text = line.strip()
    if not text:
        return None
    for level in compiled_levels:
        for rule in level.rules:
            match = rule.regex.search(text)
            if not match:
                continue
            rendered = match.expand(rule.replacement).strip()
            rendered = normalize_title(rendered, text)
            return MatchResult(
                level_no=level.level_no,
                level_name=level.level_name,
                rule=rule,
                matched_text=text,
                rendered_title=rendered,
            )
    return None


def check_line_for_toc(line: str, compiled_levels: list[CompiledLevel], max_len: int = 180) -> LineCheckResult:
    text = line.strip()
    if not text:
        return LineCheckResult(matched=None, accepted=False, reason="空行")
    if len(text) > max_len:
        return LineCheckResult(matched=None, accepted=False, reason=f"超过最大长度 {max_len}")
    matched = detect_heading_level(text, compiled_levels)
    if matched is None:
        return LineCheckResult(matched=None, accepted=False, reason="未命中规则")
    return LineCheckResult(matched=matched, accepted=True, reason="命中规则")


def _next_greater_start(items: list[TocItem], start_line: int) -> int | None:
    greater = [item.start_line for item in items if item.start_line > start_line]
    return min(greater) if greater else None


def recompute_ranges(items: list[TocItem], total_lines: int) -> list[TocItem]:
    if not items:
        return []
    sorted_items = sorted(items, key=lambda item: (item.start_line, item.level))
    for item in sorted_items:
        nxt = _next_greater_start(sorted_items, item.start_line)
        item.end_line = (nxt - 1) if nxt is not None else (total_lines - 1)
        if item.end_line < item.start_line:
            item.end_line = item.start_line
    return sorted_items


def parse_toc_items(lines: list[str], rule_levels: Iterable[RuleLevel] | None = None) -> list[TocItem]:
    if not lines:
        return []
    levels = list(rule_levels or default_rule_levels())
    compiled_levels = compile_rule_levels(levels)
    if not compiled_levels:
        return [TocItem(title="正文", start_line=0, end_line=len(lines) - 1, level=1, level_name="章节")]

    detected: list[TocItem] = []
    for idx, line in enumerate(lines):
        checked = check_line_for_toc(line, compiled_levels)
        if not checked.accepted or checked.matched is None:
            continue
        detected.append(
            TocItem(
                title=checked.matched.rendered_title,
                start_line=idx,
                end_line=idx,
                level=checked.matched.level_no,
                level_name=checked.matched.level_name,
            )
        )

    if not detected:
        deepest = compiled_levels[-1]
        return [
            TocItem(
                title="正文",
                start_line=0,
                end_line=len(lines) - 1,
                level=deepest.level_no,
                level_name=deepest.level_name,
            )
        ]
    return recompute_ranges(detected, len(lines))


def build_toc_groups(items: list[TocItem]) -> list[TocGroup]:
    groups: list[TocGroup] = []
    current_volume: TocGroup | None = None
    for item in sorted(items, key=lambda entry: (entry.start_line, entry.level)):
        if item.level == 1:
            current_volume = TocGroup(volume_title=normalize_title(item.title, "未命名卷"), chapters=[])
            groups.append(current_volume)
            continue
        if current_volume is None:
            current_volume = TocGroup(volume_title=None, chapters=[])
            groups.append(current_volume)
        current_volume.chapters.append(item)
    return groups

