#!/usr/bin/env python3
"""深入分析V1算法的成功因素"""
import sys
sys.path.insert(0, '.')

from app.subtitle_aligner import (
    align_script_to_entries, 
    parse_srt_text, 
    prepare_script_text,
    find_similar_content
)

# Load data
script_md = open('test_input/script-test.md').read()
srt_raw = open('test_input/input.srt').read()
prepared_script = prepare_script_text(script_md)
entries = parse_srt_text(srt_raw)

print("V1算法详细分析:")
print("="*70)

# 测试前几个条目，看看V1如何匹配
for i in range(5):
    entry = entries[i]
    original = entry.plain_text
    matched = find_similar_content(original, prepared_script)
    
    print(f"\n条目 {entry.index}:")
    print(f"  原文: {original}")
    print(f"  匹配: {matched}")
    print(f"  长度: {len(original)} -> {len(matched)}")

# 运行完整V1算法
chunks = align_script_to_entries(prepared_script, entries)

# 统计结果
print("\n" + "="*70)
print("V1算法统计:")
print(f"字幕条目数: {len(entries)}")
print(f"生成块数: {len(chunks)}")
print(f"非空块数: {sum(1 for c in chunks if c)}")
print(f"平均块长度: {sum(len(c) for c in chunks) / len(chunks):.1f}")
