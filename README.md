# Subtitle Review Tool

本项目提供一个本地字幕校对工具，包含 Web 端上传界面、算法脚本以及基准测试脚本。

## 目录结构

- `app/`：主程序源码（`server.py` 本地 HTTP 服务，`subtitle_aligner.py` V1 语义对齐算法，`subtitle_core.py` 通用 SRT 工具）。
- `docs/`：算法与实现相关文档报告。
- `scripts/`：命令行工具（如 `run_benchmark.py`，用于对人工基准进行评分）。
- `tests/`：辅助测试脚本（算法快速验证、上传接口测试等）。
- `static/`、`templates/`：Web 界面资源。

## 本地运行

1. 安装依赖（确保已安装 `uv`，或使用其它包管理器安装 `requests` 等所需库）：
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务：
   ```bash
   ./start.sh
   ```
   默认监听 `http://localhost:5001`，如需自定义端口可以在运行前设置 `PORT` 环境变量。
3. 停止服务：
   ```bash
   ./stop.sh
   ```

## 算法与基准

当前线上仅使用 V1 语义匹配算法。要与人工校正字幕进行对比，可运行：
```bash
python3 scripts/run_benchmark.py
```
默认会读取 `baseline/` 下的脚本、输入字幕和人工字幕，统计整体相似度。

## 目录清理与提交

仓库已自带 `.gitignore`，忽略虚拟环境、缓存、日志等文件，提交前可使用：
```bash
git status
git add .
git commit -m "your message"
git push origin main
```
