"""
Subtitle alignment with semantic matching and character count preservation.
"""
from __future__ import annotations

import re
from typing import List

from .subtitle_core import SubtitleEntry, format_entries, format_srt, parse_srt_text, wrap_chunk


def prepare_script_text(script_markdown: str) -> str:
    """Normalize a Markdown script into a single string for slicing."""
    cleaned_lines: List[str] = []
    for line in script_markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and "]" in stripped:
            stripped = stripped.split("]", 1)[1].strip()
        if stripped:
            cleaned_lines.append(stripped)
    text = " ".join(cleaned_lines)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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


def find_similar_content(original_text: str, script_text: str) -> str:
    """
    Find the most similar content in script_text for original_text.
    Uses fuzzy matching with better accuracy.
    """
    from difflib import SequenceMatcher

    target_length = len(original_text)
    best_match = ""
    best_ratio = 0
    best_completeness = 0  # Add completeness score

    # First, try to find the original text (or close to it) in script
    if original_text in script_text:
        idx = script_text.find(original_text)
        return script_text[idx:idx + target_length]

    # Try sliding window with larger context
    # This helps find better matches even when there are errors
    for i in range(len(script_text) - target_length + 1):
        candidate = script_text[i:i + target_length]

        # Calculate base similarity
        ratio = SequenceMatcher(None, original_text, candidate).ratio()

        # Also check if the candidate contains key parts of original
        key_parts_score = 0
        original_parts = split_into_parts(original_text)
        for part in original_parts:
            if len(part) >= 2 and part in candidate:
                key_parts_score += 0.2

        # Check completeness: how well does candidate preserve order of original
        completeness = calculate_completeness(original_text, candidate)

        # Combine scores
        total_score = ratio + key_parts_score + completeness * 0.1

        # Update best match with tie-breaking
        if total_score > best_ratio or (abs(total_score - best_ratio) < 0.01 and completeness > best_completeness):
            best_ratio = total_score
            best_match = candidate
            best_completeness = completeness

    # If still no good match, try with slightly different lengths
    if best_ratio < 0.4:
        for offset in range(-3, 4):
            if offset == 0:
                continue
            test_length = target_length + offset
            if test_length <= 0 or test_length > len(script_text):
                continue

            for i in range(len(script_text) - test_length + 1):
                candidate = script_text[i:i + test_length]
                if len(candidate) > target_length:
                    candidate = candidate[:target_length]
                elif len(candidate) < target_length:
                    candidate = candidate.ljust(target_length)

                ratio = SequenceMatcher(None, original_text, candidate).ratio()
                completeness = calculate_completeness(original_text, candidate)
                total_score = ratio + completeness * 0.1

                if total_score > best_ratio or (abs(total_score - best_ratio) < 0.01 and completeness > best_completeness):
                    best_ratio = total_score
                    best_match = candidate
                    best_completeness = completeness

    return best_match


def calculate_completeness(original: str, candidate: str) -> float:
    """
    Calculate how well candidate preserves the order of characters from original.
    Higher score means better preservation of character order.
    """
    if not original or not candidate:
        return 0.0

    # Find longest common subsequence to measure order preservation
    from difflib import SequenceMatcher
    matcher = SequenceMatcher(None, original, candidate)
    matches = matcher.get_matching_blocks()

    # Calculate how many characters from original are in correct order in candidate
    preserved = 0
    last_pos = -1
    for match in matches:
        if match.size > 0:
            # Check if this match comes after the previous one in candidate
            if match.b > last_pos:
                preserved += match.size
                last_pos = match.b

    return preserved / len(original)


def split_into_parts(text: str) -> List[str]:
    """Split text into meaningful parts for better matching."""
    # Split by common Chinese particles and punctuation
    parts = re.split(r'[，。！？；、\s""''（）()《》〈〉—-]+', text)
    # Filter out very short parts
    return [p for p in parts if len(p) >= 2]


def extract_key_words(text: str) -> List[str]:
    """Extract meaningful keywords from text."""
    # Remove common particles and extract meaningful words
    words = re.split(r'[，。！？；、\s""''（）()《》〈〉—-]+', text)
    # Filter out very short words and empty strings
    return [w for w in words if len(w) >= 2]


def align_script_to_entries(script_text: str, entries: List[SubtitleEntry]) -> List[str]:
    """
    Align script to entries by finding similar content.
    Preserves timing, line count, and character count structure.
    """
    chunks: List[str] = []
    for entry in entries:
        original = entry.plain_text
        # Find similar content in script
        similar = find_similar_content(original, script_text)
        refined = refine_chunk(original, similar, script_text)
        chunks.append(refined)
    return chunks


def wrap_chunk(
    chunk: str,
    line_count: int,
    manual_lines: Optional[List[str]] = None,
) -> List[str]:
    """Wrap chunk into lines, preserving original line count."""
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

    # Split text into line_count parts while preserving character count
    segments: List[str] = []
    if len(text) <= line_count:
        # If text is too short, pad with empty strings
        segments = [text[i] if i < len(text) else "" for i in range(line_count)]
    else:
        # Calculate target length for each line
        target_len = len(text) // line_count
        remainder = len(text) % line_count

        # Split text
        cursor = 0
        for i in range(line_count):
            # Distribute remainder characters
            current_len = target_len + (1 if i < remainder else 0)
            segment = text[cursor:cursor + current_len]
            segments.append(segment)
            cursor += current_len

    # Add <b> tags
    formatted: List[str] = []
    for idx, seg in enumerate(segments):
        if idx == 0:
            formatted.append(f"<b>{seg}")
        elif idx == line_count - 1:
            formatted.append(f"{seg}</b>")
        else:
            formatted.append(seg)
    return formatted


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


SUFFIX_CANDIDATES = "吗嗎嗎呢啦喇啊呀啰啵啲！!？?。．."
LEADING_PUNCT = "，,。.!！？?；;：:、… “”\"'（）()《》〈〉-—  "


def refine_chunk(original: str, candidate: str, script_text: str) -> str:
    stripped_original = original.strip()
    if not candidate.strip():
        short = stripped_original
        if short and len(short) <= 6:
            idx = script_text.find(short)
            if idx != -1:
                return script_text[idx:idx + len(short)]
        return candidate

    refined = candidate
    refined = _trim_leading_noise(refined, stripped_original)
    refined = _align_suffix(refined, stripped_original, script_text)
    return refined


def _trim_leading_noise(text: str, target: str) -> str:
    trimmed = text
    target_start = target[:1]
    while trimmed and trimmed[0] in LEADING_PUNCT and trimmed[0] != target_start:
        trimmed = trimmed[1:]
    return trimmed


def _align_suffix(candidate: str, original: str, script_text: str) -> str:
    original = original.strip()
    if not original:
        return candidate

    last_char = original[-1]
    trimmed_candidate = candidate.rstrip()

    if last_char in SUFFIX_CANDIDATES and not trimmed_candidate.endswith(last_char):
        idx = script_text.find(candidate)
        if idx != -1:
            suffix_pos = idx + len(candidate)
            if suffix_pos < len(script_text):
                next_char = script_text[suffix_pos]
                if next_char == last_char:
                    trimmed_candidate = (candidate + last_char).strip()
    return trimmed_candidate


__all__ = [
    "SubtitleEntry",
    "prepare_script_text",
    "parse_srt_text",
    "align_script_to_entries",
    "find_similar_content",
    "wrap_chunk",
    "format_entries",
    "format_srt",
]
