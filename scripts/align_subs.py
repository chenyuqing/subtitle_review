#!/usr/bin/env python3
"""
CLI helper to align a reference script with an SRT file.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from subtitle_aligner import (
    align_script_to_entries,
    format_srt,
    parse_srt_text,
    prepare_script_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Correct an SRT file using a reference script.")
    parser.add_argument("--srt", required=True, type=Path, help="Original erroneous SRT.")
    parser.add_argument("--script", required=True, type=Path, help="Reference script markdown.")
    parser.add_argument("--out", required=True, type=Path, help="Corrected SRT output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    srt_text = args.srt.read_text(encoding="utf-8")
    script_text = args.script.read_text(encoding="utf-8")
    entries = parse_srt_text(srt_text)
    prepared_script = prepare_script_text(script_text)
    chunks = align_script_to_entries(prepared_script, entries)
    corrected_srt = format_srt(entries, chunks)
    args.out.write_text(corrected_srt, encoding="utf-8")
    print(f"Wrote corrected subtitles to {args.out}")


if __name__ == "__main__":
    main()
