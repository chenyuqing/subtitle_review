#!/usr/bin/env python3
"""
Analyze low-scoring subtitles for V1 alignment.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.translation import TranslationError, translate_subtitles_to_cantonese
from app.subtitle_aligner import align_script_to_entries, prepare_script_text
from app.subtitle_core import SubtitleEntry, parse_srt_text, wrap_chunk


@dataclass
class Sample:
    name: str
    script_path: Path
    input_sub_path: Path
    groundtruth_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump low-scoring entries compared to ground truth.")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path("baseline"),
        help="Directory containing scripts/, input_subtitles/, groundtruth/ folders.",
    )
    parser.add_argument(
        "--low-threshold",
        type=float,
        default=0.5,
        help="Print entries below this score (低分重点).",
    )
    parser.add_argument(
        "--mid-min",
        type=float,
        default=0.7,
        help="中高分区间下限（含）。",
    )
    parser.add_argument(
        "--mid-max",
        type=float,
        default=0.95,
        help="中高分区间上限（不含）。",
    )
    parser.add_argument(
        "--translate-subtitles",
        action="store_true",
        help="先将普通话字幕翻译为粤语再分析（使用 DeepSeek 缓存）。",
    )
    return parser.parse_args()


def discover_samples(base_dir: Path) -> List[Sample]:
    scripts_dir = base_dir / "scripts"
    input_dir = base_dir / "input_subtitles"
    if not input_dir.exists():
        input_dir = base_dir / "input_subtiles"
    gt_dir = base_dir / "groundtruth"

    if not scripts_dir.exists() or not input_dir.exists() or not gt_dir.exists():
        raise FileNotFoundError("baseline 目录必须包含 scripts/, input_subtitles/ (或 input_subtiles/), groundtruth/ 三个子目录。")

    samples: List[Sample] = []
    for script_file in sorted(scripts_dir.glob("*")):
        if script_file.is_dir():
            continue
        stem = _normalize_name(script_file.stem)
        input_file = _first_existing(input_dir, [f"{stem}.srt", f"{stem}_input.srt", f"{script_file.stem}.srt"])
        gt_file = _first_existing(
            gt_dir,
            [f"{stem}.srt", f"{stem}_gt.srt", f"{stem}_groundtruth.srt", f"{script_file.stem}.srt"],
        )
        if not input_file or not gt_file:
            continue
        samples.append(
            Sample(
                name=stem,
                script_path=script_file,
                input_sub_path=input_file,
                groundtruth_path=gt_file,
            )
        )
    if not samples:
        raise RuntimeError("未在 baseline 数据集中找到匹配的 SRT/脚本文件。")
    return samples


def _normalize_name(name: str) -> str:
    for suffix in ("_script", "_input", "_gt", "_groundtruth"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _first_existing(directory: Path, candidates: List[str]) -> Path | None:
    for filename in candidates:
        path = directory / filename
        if path.exists():
            return path
    return None


def evaluate_sample(
    sample: Sample,
    low_threshold: float,
    mid_min: float,
    mid_max: float,
    translate_subtitles: bool = False,
) -> None:
    script_text = sample.script_path.read_text(encoding="utf-8")
    input_srt = sample.input_sub_path.read_text(encoding="utf-8")
    gt_srt = sample.groundtruth_path.read_text(encoding="utf-8")

    if translate_subtitles:
        try:
            input_srt = translate_subtitles_to_cantonese(input_srt)
        except TranslationError as exc:
            raise RuntimeError(f"{sample.name}: 字幕翻译失败 - {exc}") from exc

    entries = parse_srt_text(input_srt)
    gt_entries = parse_srt_text(gt_srt)
    if len(entries) != len(gt_entries):
        raise ValueError(f"{sample.name}: 输入字幕与基准字幕行数不一致。")

    prepared_script = prepare_script_text(script_text)
    chunks = align_script_to_entries(prepared_script, entries)

    print("=" * 80)
    print(f"Sample: {sample.name}")
    print("=" * 80)

    low_entries = 0
    mid_entries = 0
    for entry, chunk, gt_entry in zip(entries, chunks, gt_entries):
        wrapped = wrap_chunk(chunk, entry.line_count)
        plain_pred = _normalize_plain(" ".join(wrapped))
        plain_gt = _normalize_plain(" ".join(gt_entry.text_lines))
        ratio = SequenceMatcher(None, plain_pred, plain_gt).ratio()
        if ratio < low_threshold:
            low_entries += 1
            _print_entry(entry, gt_entry, wrapped, ratio, script_text, chunk, note="低分条目")
        elif mid_min <= ratio < mid_max:
            if mid_entries == 0:
                print("\n--- 中高分条目（需要微调） ---")
            mid_entries += 1
            _print_entry(entry, gt_entry, wrapped, ratio, script_text, chunk, note="中高分")
    if low_entries == 0:
        print("没有低于阈值的条目。")


def _normalize_plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def _extract_context(script_text: str, chunk: str, window: int = 40) -> str:
    cleaned_chunk = chunk.strip()
    if not cleaned_chunk:
        return ""
    pos = script_text.find(cleaned_chunk)
    if pos == -1:
        return cleaned_chunk[:window]
    start = max(0, pos - window)
    end = min(len(script_text), pos + len(cleaned_chunk) + window)
    return script_text[start:end].replace("\n", " ")


def _print_entry(
    entry: SubtitleEntry,
    gt_entry: SubtitleEntry,
    predicted_lines: List[str],
    ratio: float,
    script_text: str,
    chunk: str,
    note: str,
) -> None:
    print(f"\n[{note}] 条目 #{entry.index} | 相似度: {ratio:.3f}")
    print(f"时间轴: {entry.start} --> {entry.end}")
    print(f"原字幕: {entry.plain_text}")
    print(f"人工:    {' '.join(gt_entry.text_lines)}")
    print(f"输出:    {' '.join(predicted_lines) or '(空)'}")
    context = _extract_context(script_text, chunk, window=40)
    if context:
        print(f"脚本片段: …{context}…")


def main() -> None:
    args = parse_args()
    samples = discover_samples(args.baseline_dir)
    for sample in samples:
        evaluate_sample(
            sample,
            args.low_threshold,
            args.mid_min,
            args.mid_max,
            translate_subtitles=args.translate_subtitles,
        )


if __name__ == "__main__":
    main()
