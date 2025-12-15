from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from openai import OpenAI

from ..subtitle_core import parse_srt_text

APP_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = APP_DIR.parent
BASELINE_INPUT = ROOT_DIR / "baseline" / "input_subtiles" / "letter_0_input.srt"
BASELINE_GT = ROOT_DIR / "baseline" / "groundtruth" / "letter_0_gt.srt"
ENV_PATH = ROOT_DIR / ".env"

_ENV_LOADED = False


def _load_env_file() -> None:
    """Simple .env loader so local runs pick up DEEPSEEK_API_KEY."""

    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if ENV_PATH.exists():
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    _ENV_LOADED = True


def _load_baseline_example(max_entries: int = 3) -> Optional[str]:
    """Provide a short Mandarin->Cantonese example for prompting."""

    try:
        src_entries = parse_srt_text(BASELINE_INPUT.read_text(encoding="utf-8"))
        tgt_entries = parse_srt_text(BASELINE_GT.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    count = min(max_entries, len(src_entries), len(tgt_entries))
    if count == 0:
        return None
    examples = []
    for idx in range(count):
        src_line = " / ".join(src_entries[idx].text_lines)
        tgt_line = " / ".join(tgt_entries[idx].text_lines)
        examples.append(f"{idx + 1}. 普通话：{src_line}\n   粤语：{tgt_line}")
    return "\n".join(examples)


_BASELINE_EXAMPLE = _load_baseline_example()
CHUNK_SIZE = 80
FULL_PASS_THRESHOLD = 120

PROMPT_TEMPLATE = """你是专业字幕翻译器，任务是把普通话字幕翻译成粤语白话（简体字）。请严格遵守：
1. 保留原先的序号、时间轴（例如 00:00:22,699 --> 00:00:24,533）、HTML 标签（例如 <b>…</b>）和行结构，只替换文字内容。
2. 输出必须是口语化的粤语白话（简体写法），例如“我/你/他”可译作“我/你/佢”；保持语气词和口语表达自然顺畅。
3. 参考以下普通话→粤语示例，这些内容仅供参考，不要在输出中重复示例本身：
{example_block}
4. 标点和空白需沿用原文；若原行为空或只有标签，保持原样。
5. 输出只包含翻译后的字幕内容，不要附加解释或任何额外文字。
{extra_note}

需要翻译的完整字幕如下：
{subtitle_text}
"""


class TranslationError(RuntimeError):
    pass


def translate_subtitles_to_cantonese(subtitle_text: str) -> str:
    """Translate uploaded subtitles to Cantonese via DeepSeek."""

    if not subtitle_text.strip():
        return subtitle_text

    original_entries = parse_srt_text(subtitle_text)
    _load_env_file()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise TranslationError("缺少 DEEPSEEK_API_KEY，无法调用翻译服务。")

    example_block = _BASELINE_EXAMPLE or "（示例暂缺，但仍需保持字幕格式不变。）"
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def _translate_block(block_text: str, extra_note: str = "") -> str:
        prompt = PROMPT_TEMPLATE.format(
            example_block=example_block,
            subtitle_text=block_text,
            extra_note=extra_note,
        )
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a professional Cantonese subtitle translator."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                stream=False,
            )
        except Exception as exc:  # pragma: no cover - network failure
            raise TranslationError(f"调用 DeepSeek 失败：{exc}") from exc
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise TranslationError("翻译结果为空，请稍后重试。")
        return content

    if len(original_entries) <= FULL_PASS_THRESHOLD:
        first_pass = _translate_block(subtitle_text)
        try:
            translated_entries = parse_srt_text(first_pass)
            if len(translated_entries) == len(original_entries):
                return first_pass
        except Exception:
            pass  # fallback to chunk translation

    # Fallback: translate in manageable chunks to preserve structure.
    combined_blocks: List[str] = []
    total_chunks = (len(original_entries) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for idx in range(0, len(original_entries), CHUNK_SIZE):
        chunk_entries = original_entries[idx : idx + CHUNK_SIZE]
        chunk_lines: List[str] = []
        for entry in chunk_entries:
            block = [str(entry.index), f"{entry.start} --> {entry.end}", *entry.text_lines, ""]
            chunk_lines.extend(block)
        chunk_text = "\n".join(chunk_lines).strip() + "\n"
        chunk_no = idx // CHUNK_SIZE + 1
        extra_note = f"\n（当前为第 {chunk_no}/{total_chunks} 部分，只需翻译以下条目，勿更改任意编号或时间轴。）"
        chunk_result = _translate_block(chunk_text, extra_note=extra_note)
        parsed_chunk = parse_srt_text(chunk_result)
        if len(parsed_chunk) != len(chunk_entries):
            raise TranslationError("分段翻译输出结构异常，请稍后重试。")
        combined_blocks.append(chunk_result.strip())
    return "\n\n".join(combined_blocks).strip() + "\n"
