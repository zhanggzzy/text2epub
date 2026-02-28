from __future__ import annotations

from pathlib import Path
from typing import Callable

import chardet


ProgressCallback = Callable[[int], None]


def detect_encoding(file_path: str) -> str:
    path = Path(file_path)
    with path.open("rb") as fh:
        sample = fh.read(1024 * 1024)
    if not sample:
        raise ValueError("文件为空")

    result = chardet.detect(sample)
    encoding = (result.get("encoding") or "").lower()
    confidence = float(result.get("confidence") or 0.0)

    if "utf" in encoding:
        return "utf-8-sig"
    if "gb" in encoding or "cp936" in encoding:
        return "gbk"
    if confidence >= 0.5 and encoding:
        return encoding

    for fallback in ("utf-8-sig", "gbk"):
        try:
            sample.decode(fallback)
            return fallback
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码（仅支持 UTF-8/GBK）")


def load_txt_lines(
    file_path: str,
    progress_callback: ProgressCallback | None = None,
    chunk_size: int = 64 * 1024,
) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(file_path)

    file_size = path.stat().st_size
    if file_size <= 0:
        raise ValueError("TXT 文件为空")

    encoding = detect_encoding(file_path)
    chunks: list[bytes] = []
    read_size = 0

    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk_size)
            if not block:
                break
            chunks.append(block)
            read_size += len(block)
            if progress_callback:
                progress = min(99, int(read_size * 100 / file_size))
                progress_callback(progress)

    raw_data = b"".join(chunks)
    text = raw_data.decode(encoding, errors="strict")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    lines = text.split("\n")

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        raise ValueError("TXT 文件为空")

    if progress_callback:
        progress_callback(100)
    return lines

