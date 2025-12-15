#!/usr/bin/env python3
"""快速验证 V1 对齐算法输出质量。"""
from __future__ import annotations

import sys
from difflib import SequenceMatcher

sys.path.insert(0, ".")

from app.subtitle_aligner import align_script_to_entries, parse_srt_text, prepare_script_text


def calc_similarity(a: str, b: str) -> float:
    norm_a = "".join(a.split())
    norm_b = "".join(b.split())
    if not norm_a and not norm_b:
        return 1.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


script_md = open("test_input/script-test.md", encoding="utf-8").read()
srt_raw = open("test_input/input.srt", encoding="utf-8").read()
prepared_script = prepare_script_text(script_md)
entries = parse_srt_text(srt_raw)

print(f"测试数据: {len(entries)} 条字幕, 脚本长度 {len(prepared_script)} 字符\n")

chunks_v1 = align_script_to_entries(prepared_script, entries)
scores_v1 = []
for entry, chunk in zip(entries, chunks_v1):
    scores_v1.append(calc_similarity(chunk, entry.plain_text))

avg_v1 = sum(scores_v1) / len(scores_v1)
print("=== V1 算法输出 ===")
print(f"平均相似度: {avg_v1:.3f}")
print(f"最佳匹配: {max(scores_v1):.3f}")
print(f"最差匹配: {min(scores_v1):.3f}")

best_idx = scores_v1.index(max(scores_v1))
worst_idx = scores_v1.index(min(scores_v1))

print(f"\n最佳条目 #{entries[best_idx].index}")
print(f"  原文: {entries[best_idx].plain_text}")
print(f"  校正: {chunks_v1[best_idx]}")

print(f"\n最差条目 #{entries[worst_idx].index}")
print(f"  原文: {entries[worst_idx].plain_text}")
print(f"  校正: {chunks_v1[worst_idx]}")

print("\n提示：若需改进，可在此脚本中引入新的 V1 扩展策略再比较分数。")
