from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

BREAK_CHARS = set("，,。.!！？?；;：:、… “”\"'（）()《》〈〉-—  ")


@dataclass
class SubtitleEntry:
    index: int
    start: str
    end: str
    text_lines: List[str]

    @property
    def plain_text(self) -> str:
        text = "\n".join(self.text_lines)
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\s+", "", text)

    @property
    def line_count(self) -> int:
        return len(self.text_lines)

    @property
    def duration_ms(self) -> int:
        def parse_time(ts: str) -> int:
            hours, minutes, rest = ts.split(":")
            seconds, millis = rest.split(",")
            return (
                int(hours) * 3600 * 1000
                + int(minutes) * 60 * 1000
                + int(seconds) * 1000
                + int(millis)
            )

        return parse_time(self.end) - parse_time(self.start)


def parse_srt_text(text: str) -> List[SubtitleEntry]:
    """Parse SRT file into entries."""
    blocks = text.strip().split("\n\n")
    entries: List[SubtitleEntry] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        index = int(lines[0].strip())
        start, end = [part.strip() for part in lines[1].split("-->")]
        entries.append(
            SubtitleEntry(index=index, start=start, end=end, text_lines=lines[2:])
        )
    return entries


def wrap_chunk(
    chunk: str,
    line_count: int,
    manual_lines: Optional[List[str]] = None,
) -> List[str]:
    """Wrap text into subtitle lines with <b> tags."""
    text = chunk.strip()

    if manual_lines:
        cleaned = [line.strip() for line in manual_lines if line.strip()]
        if len(cleaned) == line_count:
            formatted = []
            for idx, seg in enumerate(cleaned):
                if idx == 0:
                    formatted.append(f"<b>{seg}")
                elif idx == line_count - 1:
                    formatted.append(f"{seg}</b>")
                else:
                    formatted.append(seg)
            return formatted

    if line_count <= 1:
        return [f"<b>{text}</b>"]

    newline_segments = text.split("\n")
    if len(newline_segments) == line_count:
        formatted: List[str] = []
        for idx, seg in enumerate(newline_segments):
            cleaned = seg.strip()
            if idx == 0:
                formatted.append(f"<b>{cleaned}")
            elif idx == line_count - 1:
                formatted.append(f"{cleaned}</b>")
            else:
                formatted.append(cleaned)
        return formatted

    segments: List[str] = []
    cursor = 0
    for line_index in range(line_count):
        remaining = line_count - line_index
        remainder = text[cursor:]
        if remaining == 1 or not remainder:
            segments.append(remainder.strip())
            cursor = len(text)
            continue
        approx = max(1, round(len(remainder) / remaining))
        split_at = find_line_split(remainder, approx)
        segments.append(remainder[:split_at].strip())
        cursor += split_at

    formatted: List[str] = []
    for idx, seg in enumerate(segments):
        if idx == 0:
            formatted.append(f"<b>{seg}")
        elif idx == line_count - 1:
            formatted.append(f"{seg}</b>")
        else:
            formatted.append(seg)
    return formatted


def find_line_split(chunk: str, approx: int) -> int:
    """Find best position to split a chunk into lines."""
    approx = max(1, min(approx, len(chunk) - 1))

    for offset in range(0, 8):
        idx = approx + offset
        if idx < len(chunk) and chunk[idx - 1] in BREAK_CHARS:
            return idx
    for offset in range(0, 8):
        idx = approx - offset
        if idx > 0 and chunk[idx - 1] in BREAK_CHARS:
            return idx
    return approx


def format_entries(
    entries: List[SubtitleEntry],
    chunks: List[str],
    manual_breaks: Optional[List[Optional[List[str]]]] = None,
) -> List[str]:
    """Format entries and chunks into SRT blocks."""
    blocks: List[str] = []
    if len(entries) != len(chunks):
        raise ValueError("Entry and chunk counts do not match.")
    for idx, (entry, chunk) in enumerate(zip(entries, chunks)):
        manual_lines = None
        if manual_breaks and idx < len(manual_breaks):
            manual_lines = manual_breaks[idx]
        wrapped = wrap_chunk(chunk, entry.line_count, manual_lines)
        block = "\n".join(
            [
                str(entry.index),
                f"{entry.start} --> {entry.end}",
                *wrapped,
            ]
        )
        blocks.append(block)
    return blocks


def format_srt(
    entries: List[SubtitleEntry],
    chunks: List[str],
    manual_breaks: Optional[List[Optional[List[str]]]] = None,
) -> str:
    """Format entries and chunks into complete SRT text."""
    blocks = format_entries(entries, chunks, manual_breaks)
    return "\n\n".join(blocks) + "\n"


__all__ = [
    "BREAK_CHARS",
    "SubtitleEntry",
    "parse_srt_text",
    "wrap_chunk",
    "format_entries",
    "format_srt",
]
