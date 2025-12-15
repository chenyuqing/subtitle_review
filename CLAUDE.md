# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a subtitle review and correction tool that aligns reference scripts with SRT subtitle files. It corrects subtitle text by mapping script content to subtitle entries while preserving SRT structure (timing, numbering, formatting with `<b>` tags).

The system provides two interfaces:
- **Web UI**: Upload script + SRT → Review aligned results → Download corrected SRT
- **CLI**: Command-line tool for batch processing

## Common Commands

### Starting the Web Server
```bash
./start.sh
# Server runs on http://localhost:5000 (configurable via HOST/PORT env vars)
```

### Stopping the Web Server
```bash
./stop.sh
```

### Running Server Manually
```bash
python server.py --host 127.0.0.1 --port 5000
```

### Using CLI Tool
```bash
python scripts/align_subs.py --srt test_input/input.srt --script test_input/script-test.md --out corrected.srt
```

### Virtual Environment
- Uses `uv` package manager (must be installed separately)
- Virtual environment at `.venv/`
- Python dependencies from `requirements.txt` (currently empty - uses only standard library)

## Code Architecture

### Core Components

**subtitle_aligner.py** - Core text processing and alignment logic
- `SubtitleEntry`: Dataclass representing SRT entries with timing and text
- `prepare_script_text()`: Normalizes Markdown scripts by removing headers and speaker tags
- `parse_srt_text()`: Parses SRT files into structured SubtitleEntry objects
- `align_script_to_entries()`: Distributes script text across subtitle entries using weighted proportional allocation
- `format_entries()` / `format_srt()`: Formats aligned text back into SRT format with proper `<b>` tag wrapping
- `wrap_chunk()`: Handles multi-line text wrapping with intelligent breaking at punctuation

**server.py** - Web server and HTTP API
- `SubtitleRequestHandler`: Custom HTTP server handling:
  - `GET /`: Upload form
  - `POST /review`: File upload, processing, and review page rendering
  - `POST /save`: Saves edited results and generates preview
  - `POST /download`: Downloads corrected SRT file
- Custom multipart/form-data parser (no external dependencies)
- Base64 payload encoding for state management between pages
- Inline HTML templates (no separate template files)

**scripts/align_subs.py** - CLI interface
- Simple argparse wrapper around subtitle_aligner functions
- Reads script + SRT → generates corrected SRT

### Data Flow

1. **Upload**: User uploads Markdown script and SRT file
2. **Parsing**: `prepare_script_text()` cleans script; `parse_srt_text()` extracts SRT structure
3. **Alignment**: `align_script_to_entries()` distributes script text across entries using:
   - Weight calculation based on text length and subtitle duration
   - Proportional text allocation with intelligent sentence breaking
4. **Review**: Web UI shows original vs corrected text with manual editing capability
5. **Formatting**: `format_entries()` reconstructs SRT with proper `<b>` tag wrapping
6. **Output**: Download as corrected `.srt` file

### Key Implementation Details

- **No external dependencies**: All code uses Python standard library only
- **Text normalization**: Removes HTML tags, normalizes whitespace, handles Chinese punctuation
- **Smart text breaking**: Preserves punctuation and line length limits for readability
- **Structure preservation**: Maintains original SRT timing, numbering, and line counts
- **State management**: Uses base64-encoded JSON payloads to persist review state

## Project Structure

```
subtitle-review/
├── server.py              # Web server and HTTP handler
├── subtitle_aligner.py    # Core alignment algorithm
├── scripts/
│   └── align_subs.py     # CLI tool
├── static/
│   └── styles.css        # Minimal styling
├── templates/            # (empty - templates inline in server.py)
├── test_input/           # Sample files for testing
│   ├── script-test.md
│   └── input.srt
├── start.sh              # Service startup script
├── stop.sh               # Service shutdown script
└── requirements.txt      # (empty - stdlib only)
```

## Testing with Sample Data

Test files are located in `test_input/`:
- `script-test.md`: Reference script (Markdown format)
- `input.srt`: Original subtitle file with errors

Use these to test alignment:
```bash
python scripts/align_subs.py \
  --srt test_input/input.srt \
  --script test_input/script-test.md \
  --out corrected.srt
```

## Development Notes

- The IMPLEMENTATION_PLAN.md contains detailed requirements and algorithm design
- Code uses type hints throughout
- Chinese language support with proper punctuation handling
- Web UI uses vanilla HTML/CSS (no frontend frameworks)
- Custom HTTP server (no Flask despite references in start.sh comments)
- Error handling: Returns HTML error pages with Chinese messages
