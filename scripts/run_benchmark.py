#!/usr/bin/env python3
"""
Benchmark subtitle alignment algorithms against ground truth subtitles.
"""
from __future__ import annotations

import argparse
import re
import statistics
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
    parser = argparse.ArgumentParser(description="Run alignment benchmark against ground truth subtitles.")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path("baseline"),
        help="Directory that contains scripts/, input_subtitles/, groundtruth/ folders.",
    )
    parser.add_argument(
        "--translate-subtitles",
        action="store_true",
        help="Use DeepSeek to translate Mandarin subtitles into Cantonese before alignment.",
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
        stem = script_file.stem
        base_name = _normalize_name(stem)
        input_file = _find_first_existing(
            input_dir,
            [f"{base_name}.srt", f"{base_name}_input.srt", f"{stem}.srt"],
        )
        gt_file = _find_first_existing(
            gt_dir,
            [f"{base_name}.srt", f"{base_name}_gt.srt", f"{base_name}_groundtruth.srt", f"{stem}.srt"],
        )
        if not input_file or not gt_file:
            continue
        samples.append(
            Sample(
                name=base_name,
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


def _find_first_existing(directory: Path, filenames: List[str]) -> Path | None:
    for filename in filenames:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def evaluate_sample(sample: Sample, translate_subtitles: bool = False) -> List[float]:
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
    if len(chunks) != len(entries):
        raise ValueError(f"{sample.name}: 输出数量与字幕条目不一致。")

    algo_scores: List[float] = []
    for entry, chunk, gt_entry in zip(entries, chunks, gt_entries):
        wrapped = wrap_chunk(chunk, entry.line_count)
        plain_pred = _normalize_plain(" ".join(wrapped))
        plain_gt = _normalize_plain(" ".join(gt_entry.text_lines))
        ratio = SequenceMatcher(None, plain_pred, plain_gt).ratio()
        algo_scores.append(ratio)
    return algo_scores


def _normalize_plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def summarize_scores(all_scores: Dict[str, List[float]]) -> None:
    header = "=" * 60
    print(header)
    print("基准测试结果 (与人工字幕对比)")
    print(header)
    print(f"{'算法':<10} {'平均分':>10} {'中位数':>10} {'最高分':>10} {'最低分':>10}")
    print("-" * 60)
    for algo, scores in all_scores.items():
        avg = statistics.mean(scores)
        median = statistics.median(scores)
        best = max(scores)
        worst = min(scores)
        print(f"{algo.upper():<10} {avg:>10.3f} {median:>10.3f} {best:>10.3f} {worst:>10.3f}")
    print()


def main() -> None:
    args = parse_args()
    samples = discover_samples(args.baseline_dir)

    algo_key = "v1_translated" if args.translate_subtitles else "v1"
    aggregated: Dict[str, List[float]] = {algo_key: []}

    for sample in samples:
        algo_scores = evaluate_sample(sample, translate_subtitles=args.translate_subtitles)
        aggregated[algo_key].extend(algo_scores)

    summarize_scores(aggregated)


if __name__ == "__main__":
    main()
