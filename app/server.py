from __future__ import annotations

import argparse
import copy
import html
import io
import logging
import os
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

from .services.translation import TranslationError, translate_subtitles_to_cantonese
from .subtitle_aligner import align_script_to_entries, prepare_script_text
from .subtitle_core import SubtitleEntry, format_entries, parse_srt_text

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
STATIC_DIR = ROOT_DIR / "static"
MAX_UPLOAD_SIZE = 8 * 1024 * 1024  # 8MB per request
SESSION_TTL_SECONDS = 60 * 60

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("subtitle-review")


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, data: Dict[str, Any]) -> str:
        session_id = secrets.token_urlsafe(16)
        payload = copy.deepcopy(data)
        payload["created_at"] = time.time()
        with self._lock:
            self._cleanup_locked()
            self._sessions[session_id] = payload
        return session_id

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            if time.time() - session["created_at"] > SESSION_TTL_SECONDS:
                del self._sessions[session_id]
                return None
            return copy.deepcopy(session)

    def set(self, session_id: str, data: Dict[str, Any]) -> bool:
        payload = copy.deepcopy(data)
        payload["created_at"] = time.time()
        with self._lock:
            if session_id not in self._sessions:
                return False
            self._cleanup_locked()
            self._sessions[session_id] = payload
        return True

    def _cleanup_locked(self) -> None:
        now = time.time()
        expired = [sid for sid, data in self._sessions.items() if now - data.get("created_at", 0) > SESSION_TTL_SECONDS]
        for sid in expired:
            del self._sessions[sid]


SESSION_STORE = SessionStore()


def build_entry_payload(entries: List[SubtitleEntry], chunks: List[str]) -> List[Dict[str, Any]]:
    payload_entries: List[Dict[str, Any]] = []
    for entry, chunk in zip(entries, chunks):
        payload_entries.append(
            {
                "index": entry.index,
                "start": entry.start,
                "end": entry.end,
                "line_count": entry.line_count,
                "text_lines": entry.text_lines,
                "original_text": "\n".join(entry.text_lines),
                "script_chunk": chunk,
                "corrected_text": chunk,
            }
        )
    return payload_entries


class SimpleUpload:
    def __init__(self, filename: Optional[str], content_type: str, data: bytes) -> None:
        self.filename = filename or ""
        self.content_type = content_type
        self.data = data
        self.file = io.BytesIO(data)


class SubtitleRequestHandler(BaseHTTPRequestHandler):
    server_version = "SubtitleServer/1.0"

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            body = self.render_upload()
            self._send_html(body)
        elif self.path == "/static/styles.css":
            self.serve_static(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        if self.path == "/review":
            self.handle_review()
        elif self.path == "/save":
            self.handle_save()
        elif self.path == "/download":
            self.handle_download()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    # Helpers -----------------------------------------------------------------
    def serve_static(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Static asset not found.")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def render_upload(self, error: Optional[str] = None) -> str:
        error_html = ""
        if error:
            error_html = f'<div class="alert alert-error">{html.escape(error)}</div>'
        return f"""<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <title>字幕校对工具</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="container">
        <h1>字幕校对工具</h1>
        <p class="subtitle">上传脚本与原字幕，快速比对校正</p>
      </div>
    </header>
    <main class="container">
      {error_html}
      <section class="panel">
        <h2>上传文件</h2>
        <form method="post" action="/review" enctype="multipart/form-data" class="upload-form">
          <label class="form-field">
            <span>脚本文件（Markdown）</span>
            <input type="file" name="script_file" accept=".md,.markdown,.txt" required />
          </label>
          <label class="form-field">
            <span>SRT 字幕文件</span>
            <input type="file" name="srt_file" accept=".srt" required />
          </label>
          <div class="form-field">
            <span>算法版本</span>
            <div class="readonly-field">
              <strong>V1 - 语义匹配算法（当前启用）</strong>
              <small>算法会自动匹配脚本与字幕，可在结果页手动微调。</small>
            </div>
          </div>
          <label class="form-field checkbox-field">
            <span class="checkbox-option">
              <input type="checkbox" name="enable_translation" value="1" />
              <span>
                <strong>自动将普通话字幕翻译为粤语白话（DeepSeek）</strong>
                <small>需在 .env 设置 DEEPSEEK_API_KEY，翻译后再进行对齐。</small>
              </span>
            </span>
          </label>
          <button type="submit" class="btn primary" id="submit-btn">开始校对</button>
        </form>
      </section>
      <script>
        document.addEventListener('DOMContentLoaded', function() {{
          const submitBtn = document.getElementById('submit-btn');

          const form = document.querySelector('.upload-form');
          if (form && submitBtn) {{
            form.addEventListener('submit', function() {{
              submitBtn.textContent = '处理中...';
              submitBtn.disabled = true;
              submitBtn.style.opacity = '0.6';
            }});
          }}
        }});
      </script>
    </main>
  </body>
</html>
"""

    def render_review(
        self,
        entries: List[Dict[str, Any]],
        session_id: str,
        message: Optional[str] = None,
        result_srt: Optional[str] = None,
        script_name: Optional[str] = None,
        srt_name: Optional[str] = None,
    ) -> str:
        alert_html = ""
        if message:
            alert_html = f'<div class="alert alert-success">{html.escape(message)}</div>'
        preview_html = ""
        if result_srt:
            escaped = html.escape(result_srt)
            dl_form = f"""
                <form method="post" action="/download">
                  <input type="hidden" name="session_id" value="{session_id}" />
                  <button type="submit" class="btn primary">下载字幕文件</button>
                </form>
                """
            preview_html = f"""
            <section class="panel">
              <h3>校正后的 SRT 预览</h3>
              <textarea readonly rows="10">{escaped}</textarea>
              {dl_form}
            </section>
            """
        cue_cards = "\n".join(self.render_entry(entry) for entry in entries)
        return f"""<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <title>字幕校对工具</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="container">
        <h1>字幕校对工具</h1>
        <p class="subtitle">上传脚本与原字幕，快速比对校正</p>
      </div>
    </header>
    <main class="container">
      {alert_html}
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>校对结果</h2>
            <p class="meta">脚本：{html.escape(script_name or '')} ｜ 原字幕：{html.escape(srt_name or '')}</p>
          </div>
          <a href="/" class="btn secondary">重新上传</a>
        </div>
      </section>
      <form method="post" action="/save" class="panel">
        <input type="hidden" name="session_id" value="{session_id}" />
        <div class="cue-list">
          {cue_cards}
        </div>
        <div class="form-actions">
          <button type="submit" class="btn primary">保存字幕</button>
        </div>
      </form>
      {preview_html}
    </main>
  </body>
</html>
"""

    def render_entry(self, entry: Dict[str, Any]) -> str:
        script_html = html.escape(entry["script_chunk"])
        original_html = html.escape(entry["original_text"]).replace("\n", "<br/>")
        corrected_html = html.escape(entry["corrected_text"])
        return f"""
        <div class="cue-card">
          <div class="cue-header">
            <span># {entry['index']}</span>
            <span>{html.escape(entry['start'])} → {html.escape(entry['end'])}</span>
          </div>
          <div class="cue-row script-row">
            <span class="row-label">脚本</span>
            <div class="row-content">{script_html}</div>
          </div>
          <div class="cue-row original-row">
            <span class="row-label">原字幕</span>
            <div class="row-content">{original_html}</div>
          </div>
          <div class="cue-row corrected-row">
            <label class="row-label" for="corrected_{entry['index']}">校正</label>
            <div class="row-content">
              <textarea id="corrected_{entry['index']}" name="corrected_{entry['index']}" rows="3">{corrected_html}</textarea>
              <small>可手动编辑（系统会自动补齐 &lt;b&gt; 标签和行数）</small>
            </div>
          </div>
        </div>
        """

    def handle_review(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            body = self.render_upload("表单格式错误，请重新上传。")
            self._send_html(body, HTTPStatus.BAD_REQUEST)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._send_html(self.render_upload("上传内容为空。"), HTTPStatus.BAD_REQUEST)
            return
        try:
            form = self._parse_multipart(length)
        except ValueError as exc:
            self._send_html(self.render_upload(str(exc)), HTTPStatus.BAD_REQUEST)
            return
        script_item = form.get("script_file")
        srt_item = form.get("srt_file")
        translate_flag_raw = form.get("enable_translation", "")
        translate_flag = str(translate_flag_raw).lower() in {"1", "true", "yes", "on"}
        if not isinstance(script_item, SimpleUpload):
            body = self.render_upload("缺少脚本文件。")
            self._send_html(body, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(srt_item, SimpleUpload):
            body = self.render_upload("缺少字幕文件。")
            self._send_html(body, HTTPStatus.BAD_REQUEST)
            return
        script_raw = script_item.file.read().decode("utf-8", errors="ignore")
        srt_raw = srt_item.file.read().decode("utf-8", errors="ignore")
        translation_message = None
        if translate_flag:
            try:
                srt_raw = translate_subtitles_to_cantonese(srt_raw)
                translation_message = "已使用 DeepSeek 将字幕翻译为粤语白话。"
            except TranslationError as exc:
                LOGGER.warning("Subtitle translation failed: %s", exc)
                body = self.render_upload(f"字幕翻译失败：{exc}")
                self._send_html(body, HTTPStatus.BAD_REQUEST)
                return

        try:
            prepared_script = prepare_script_text(script_raw)
            entries = parse_srt_text(srt_raw)

            # 当前仅提供 V1 算法
            chunks = align_script_to_entries(prepared_script, entries)
        except Exception:
            LOGGER.exception("Failed to process uploaded files")
            body = self.render_upload("处理文件时出错，请确认文件内容是否正确。")
            self._send_html(body, HTTPStatus.BAD_REQUEST)
            return
        payload_entries = build_entry_payload(entries, chunks)
        session_id = SESSION_STORE.create(
            {
                "entries": payload_entries,
                "script_name": script_item.filename or "script",
                "srt_name": srt_item.filename or "input.srt",
                "result_srt": None,
            }
        )
        page = self.render_review(
            payload_entries,
            session_id,
            message=translation_message,
            script_name=script_item.filename,
            srt_name=srt_item.filename,
        )
        self._send_html(page)

    def handle_save(self) -> None:
        data = self._parse_urlencoded()
        session_id = data.get("session_id", [""])[0]
        if not session_id:
            self._send_html(self.render_upload("缺少会话数据，请重新上传。"), HTTPStatus.BAD_REQUEST)
            return
        session = SESSION_STORE.get(session_id)
        if not session:
            self._send_html(self.render_upload("会话已过期，请重新上传。"), HTTPStatus.BAD_REQUEST)
            return
        entry_payloads: List[Dict[str, Any]] = session["entries"]
        manual_breaks: List[Optional[List[str]]] = []
        chunks: List[str] = []
        for entry in entry_payloads:
            field = f"corrected_{entry['index']}"
            value = data.get(field, [entry.get("corrected_text", "")])[0].strip()
            entry["corrected_text"] = value
            chunks.append(value)
            lines = [line.strip() for line in value.splitlines() if line.strip()]
            manual_breaks.append(lines if len(lines) == entry["line_count"] else None)
        reconstructed_entries = [
            SubtitleEntry(
                index=e["index"],
                start=e["start"],
                end=e["end"],
                text_lines=e["text_lines"],
            )
            for e in entry_payloads
        ]
        blocks = format_entries(reconstructed_entries, chunks, manual_breaks)
        result_srt = "\n\n".join(blocks) + "\n"
        session["entries"] = entry_payloads
        session["result_srt"] = result_srt
        SESSION_STORE.set(session_id, session)
        page = self.render_review(
            entry_payloads,
            session_id,
            message="字幕已保存，可继续编辑或下载。",
            result_srt=result_srt,
            script_name=session.get("script_name"),
            srt_name=session.get("srt_name"),
        )
        self._send_html(page)

    def handle_download(self) -> None:
        data = self._parse_urlencoded()
        session_id = data.get("session_id", [""])[0]
        if not session_id:
            self._send_html(self.render_upload("没有可下载的字幕数据。"), HTTPStatus.BAD_REQUEST)
            return
        session = SESSION_STORE.get(session_id)
        if not session or not session.get("result_srt"):
            self._send_html(self.render_upload("暂无可下载的字幕数据，请先保存。"), HTTPStatus.BAD_REQUEST)
            return
        decoded = session["result_srt"].encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="corrected.srt"')
        self.send_header("Content-Length", str(len(decoded)))
        self.end_headers()
        self.wfile.write(decoded)

    def _parse_multipart(self, length: int) -> Dict[str, Any]:
        if length > MAX_UPLOAD_SIZE:
            raise ValueError("上传文件过大，单次限制为 8MB。")
        content_type = self.headers.get("Content-Type", "")
        match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type)
        if not match:
            raise ValueError("表单缺少 boundary，无法解析。")
        boundary = match.group(1) or match.group(2)
        boundary_bytes = f"--{boundary}".encode("utf-8")
        body = self.rfile.read(length)
        if boundary_bytes not in body:
            raise ValueError("上传表单格式错误。")
        parts = body.split(boundary_bytes)
        parsed: Dict[str, Any] = {}
        for part in parts:
            part = part.strip()
            if not part or part == b"--":
                continue
            if part.endswith(b"--"):
                part = part[:-2]
            part = part.strip(b"\r\n")
            if not part:
                continue
            header_block, _, data = part.partition(b"\r\n\r\n")
            headers = self._parse_part_headers(header_block.decode("utf-8", errors="ignore"))
            disposition = headers.get("content-disposition", "")
            name = self._extract_disposition_param(disposition, "name")
            filename = self._extract_disposition_param(disposition, "filename")
            if not name:
                continue
            payload = data.rstrip(b"\r\n")
            if filename is not None:
                parsed[name] = SimpleUpload(
                    filename=filename,
                    content_type=headers.get("content-type", "application/octet-stream"),
                    data=payload,
                )
            else:
                parsed[name] = payload.decode("utf-8", errors="ignore")
        return parsed

    def _parse_part_headers(self, header_block: str) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        for line in header_block.split("\r\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        return headers

    def _extract_disposition_param(self, disposition: str, key: str) -> Optional[str]:
        pattern = re.compile(rf'{key}="([^"]*)"')
        match = pattern.search(disposition)
        if match:
            return match.group(1)
        return None

    def _parse_urlencoded(self) -> Dict[str, List[str]]:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        return parse_qs(body)

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # 客户端已关闭连接，忽略错误
            pass


def run_server(host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), SubtitleRequestHandler)
    print(f"Serving on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local subtitle review server.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5001")))
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
