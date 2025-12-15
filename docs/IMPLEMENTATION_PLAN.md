## 需求与目标

- **目标**：读取参考稿 `test_input/script-test.md` 与原字幕 `test_input/input.srt`，将脚本内容精准映射到每条字幕，校正错字并保持原 SRT 的编号、时间轴、分段数和 `<b>` 标签，输出新的正确字幕文件。
- **约束**：
  - SRT 结构不可变：条目顺序、序号、`HH:MM:SS,mmm` 时间轴、空行分隔全部保留。
  - 每条文本必须继续包在 `<b>…</b>` 中；若字幕本来是多行 `<b>`，同样保持。
  - 禁用外部网络；除非已有依赖，尽量使用标准库。

## 输入解析

1. **字幕**：用标准 SRT 解析（分块读取空行分隔的三段）。将每块封装为结构体 `{index, start, end, raw_text_lines}`，其中 `raw_text_lines` 是原 `<b>…</b>` 文本行数组。
2. **脚本**：解析 Markdown，仅保留正文。
   - 删除标题（如 `## …`）。
   - 去除 speaker 标记 `[erik]`。
   - 保留段落并转换为句序列。先按换行分段，再用正则按句末标点（`。？！`、`?`、`!`、`……` 等）拆分，保证粤语/口语内容不丢失。

## 文本规范化

- 对脚本句与字幕文本分别生成“原文”与“简化文本”。简化文本用于匹配：移除 HTML 标签、空白、标点，统一数字格式（如英文数字、全角），可选简繁体转换（若不引入库，可写常见字映射，如“吕/里”、“卡博斯/卡卜斯”等）。同时保留原句用于输出。

## 对齐策略

1. 字幕时间轴可信，文本错误较多，需要通过脚本句序与字幕条目序顺序对齐。
2. 实施：
   - 生成脚本句列表 `script_sentences`（顺序保持）。
   - 生成字幕条 `subs`，并对 `subs[i]` 的文本合并为干净字符串 `sub_plain`。
   - 使用滑动窗口 + `difflib.SequenceMatcher` 计算 `script_sentences[j:k]` 拼接后与 `sub_plain` 的相似度。
   - 动态规划/贪心：依次遍历字幕条目，对每个条目从尚未匹配的脚本句开头开始尝试 1~N（如 3 或 4）句合并求最高得分，选择得分最高的组合作为对齐，推进脚本索引。必要时微调窗口大小以覆盖长句段。
3. 若字幕条目多于脚本句且无法自动匹配，保留上一次句子并切分；如字幕较少则合并多句输出。

## 输出生成

- 对每个字幕条，取映射到的脚本内容，依据原字幕行数决定换行策略：若原字幕多行，按长度拆分（例如基于字数限制 12–15 字/行），但每行仍包 `<b>…</b>`。
- 填充回结构：`index`、原 `start --> end`、新的 `<b>文本</b>`。
- 写入新文件（例如 `corrected.srt`），保持空行分隔。

## 验证

- 自动检查：确认输出字幕条数与输入一致；检查每条文本均包含 `<b>` 包裹；确保所有脚本句都被消耗或记录未匹配的句子索引。
- 生成差异摘要（如 `difflib.unified_diff`）供快速人工审查。

## 目录与函数建议

- 在根目录新增脚本 `scripts/align_subs.py` 处理主流程。
- 函数结构建议：

```
def load_script(path) -> List[str]
def load_srt(path) -> List[SubtitleEntry]
def normalize(text) -> str
def align(script_sentences, subtitle_entries) -> Mapping
def format_entry(entry, new_text) -> List[str]
def main(input_srt, script_md, output_srt)
```

- 在脚本注释中记录使用方法：

```
python scripts/align_subs.py --srt test_input/input.srt --script test_input/script-test.md --out corrected.srt
```

## 实施步骤

1. 实现加载与解析函数。
2. 实现句段对齐与规范化逻辑。
3. 生成并写出新的 SRT，运行验证并输出差异摘要。
