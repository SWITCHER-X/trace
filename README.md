# Trace

**Universal File Metadata & Privacy Inspector**

> **Scan. See. Scrub. Share safely.**

Drag and drop any file — see exactly what hidden data it contains, and scrub it with one click. Runs on Windows, macOS, Linux, and Termux (Android). Everything happens **locally**. No uploads. No network. No tracking.

```text
┌──────────────────────────────────────────────────────────────────┐
│  $ trace scan photo.jpg                                          │
│                                                                  │
│  File:    photo.jpg          Size:  2.4 MB    Risk:  HIGH       │
│                                                                  │
│  ⚠  WARNINGS                                                     │
│  ▸ GPS coordinates found — photo location can be determined     │
│                                                                  │
│  📋 METADATA FOUND                                               │
│  EXIF:GPSLatitude:     37.7749° N           ████████ RISKY       │
│  EXIF:GPSLongitude:    -122.4194° W          ████████ RISKY       │
│  EXIF:Model:           iPhone 13             ████████ RISKY       │
│  EXIF:DateTime:        2026-03-15 14:32:10   ████████ RISKY       │
│  EXIF:Software:        Instagram 280.0     ████████ RISKY       │
│  EXIF:Artist:          @johndoe            ████████ RISKY       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Why Trace Exists

Every photo, PDF, and document you share carries hidden metadata:

| Metadata Type | What It Reveals | Attack It Enables |
|---------------|-----------------|-------------------|
| **EXIF GPS** | Your exact location (home, office, gym) | Stalking, doxxing, physical targeting |
| **Device Info** | Camera model, serial number, OS version | Device fingerprinting, targeted exploits |
| **Author/Creator** | Real name, username, email, organization | Spear-phishing, social engineering |
| **Timestamps** | When/where you were active | Pattern-of-life analysis, alibi contradiction |
| **Software** | Editing apps, versions, templates | Supply-chain profiling, exploit matching |

**People doxx themselves constantly without realizing it.** Existing tools are CLI-only, Windows-only, or require uploading files to sketchy websites.

Trace fixes that: **One command. Local only. Cross-platform. Open source.**

---

## Features

| Feature | Description |
|---------|-------------|
| **EXIF Scanner** | GPS coordinates, camera model, serial, timestamps, software from photos |
| **Document Inspector** | Author, company, template path, revision history in PDFs/Office docs |
| **Audio/Video Metadata** | ID3 tags, Vorbis comments, QuickTime atoms, device info |
| **Text/Archive Scan** | Shebang lines, comment headers, ZIP comments, file timestamps |
| **Risk Scoring** | HIGH / MEDIUM / LOW / NONE based on personal identifier detection |
| **One-Click Scrub** | Strips identifying metadata before you share |
| **Batch Mode** | Scan entire folders before uploading to social media |
| **JSON Output** | Machine-readable for scripting and CI/CD pipelines |
| **Web GUI** | Drag-and-drop browser interface (`trace-web`) |
| **Unit Tests** | Full test suite with pytest |
| **CI/CD** | GitHub Actions workflow for automated testing |

---

## Quick Start

### One-Line Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/your-username/trace/main/install.sh | bash
```

### Manual Install

```bash
# From PyPI (when published)
pip install trace-metadata

# From source
git clone https://github.com/your-username/trace.git
cd trace
pip install -e ".[web]"   # includes web GUI
```

### Requirements

- **Python 3.8+**
- **pip** (comes with Python)

Optional dependencies (auto-installed with `.[web]`):
- `flask` — Web GUI
- `piexif` — EXIF parsing
- `PyPDF2` — PDF metadata
- `mutagen` — Audio metadata (ID3, Vorbis)
- `python-docx` / `openpyxl` — Office docs (if needed)

---

## Usage

### CLI — Scan Files

```bash
# Single file
trace scan photo.jpg

# JSON output (for scripts/pipelines)
trace scan photo.jpg --json

# Batch scan entire folder
trace batch ./downloads/

# Quiet mode (errors only)
trace scan photo.jpg --quiet
```

### CLI — Scrub Metadata

```bash
# Scrub single file (creates photo_clean.jpg)
trace scrub photo.jpg

# Scrub to custom output
trace scrub photo.jpg -o clean_photo.jpg

# Scrub entire folder (batch)
trace batch-scrub ./uploads/ -o ./clean/
```

### Web GUI

```bash
# Launch web interface
trace-web

# Or with custom port
trace-web --port 8080
```

Open **http://localhost:5001** (or your custom port) in any browser.

**Web GUI features:**
- Drag-and-drop file upload
- Real-time metadata table with risk highlighting
- Copy-to-clipboard on any value
- One-click scrub → auto-downloads clean copy
- Keyboard shortcuts: `⌘S` Scan, `⌘H` History, `⌘G` Safety, `Esc` Clear
- Safety Guide tab explaining metadata attacks
- Works on mobile (responsive design)
- Skeleton loading screens
- Accessible: respects `prefers-reduced-motion`

---

## Supported Formats

| Category | Extensions | Metadata Extracted |
|----------|-----------|-------------------|
| **Images** | `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.webp` | Full EXIF (GPS, camera, timestamps, software, artist) |
| **Audio** | `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg` | ID3v1/v2, Vorbis comments, RIFF INFO chunks |
| **Video** | `.mp4`, `.mov`, `.mkv`, `.avi` | QuickTime atoms (title, artist, copyright, device) |
| **Documents** | `.pdf` | Author, title, subject, keywords, creator, producer, dates |
| **Office** | `.docx`, `.xlsx`, `.pptx` | Core properties (author, company, last modified by, dates) |
| **Text** | `.txt`, `.md`, `.csv`, `.py`, `.log`, `.json`, `.yaml`, `.yml` | Shebang, `# Author:`, `# Created:`, `# Copyright:`, `# Email:` |
| **Archive** | `.zip` | ZIP comment, file count, timestamps |

---

## Output Examples

### Human-Readable (Default)

```text
$ trace scan document.pdf

File:    document.pdf        Size:  4.2 MB    Risk:  MEDIUM

⚠  WARNINGS
▸ Author name found — may identify you

📋 METADATA
PDF:Producer:          PyPDF2 3.0.1
PDF:Author:            Jane Smith          ████████ RISKY
PDF:Title:             Q4 Budget Draft
PDF:Subject:           Confidential
PDF:CreationDate:      2026-01-15 09:30:00 ████████ RISKY
PDF:ModDate:           2026-01-20 14:22:00
```

### JSON Output

```json
{
  "filename": "document.pdf",
  "size": 4403200,
  "risk_level": "medium",
  "metadata": {
    "PDF:Producer": "PyPDF2 3.0.1",
    "PDF:Author": "Jane Smith",
    "PDF:Title": "Q4 Budget Draft",
    "PDF:Subject": "Confidential",
    "PDF:CreationDate": "2026-01-15 09:30:00",
    "PDF:ModDate": "2026-01-20 14:22:00"
  },
  "warnings": ["Author name found — may identify you"],
  "errors": []
}
```

### Batch Output

```text
$ trace batch ./photos/

Scanning 12 files...

IMG_001.jpg    HIGH    GPS, Device, Timestamps
IMG_002.jpg    NONE    (clean)
IMG_003.jpg    MEDIUM  Camera model, DateTime
IMG_004.jpg    HIGH    GPS, Author: @travelblogger
...

Summary: 12 scanned, 3 HIGH, 4 MEDIUM, 5 NONE
```

---

## Privacy & Security

| Guarantee | Implementation |
|-----------|----------------|
| **No uploads** | All processing happens in-process, no network calls |
| **No telemetry** | No analytics, no crash reporting, no phoning home |
| **No persistence** | Files read from disk, processed in memory, results returned |
| **Open source** | Full source auditable at `github.com/your-username/trace` |
| **Local-first** | Web GUI serves from `127.0.0.1` only by default |

> **Disclaimer:** Trace is a privacy aid, not a guarantee of anonymity. Some metadata may be embedded in ways not detectable by this tool (steganography, custom chunks, proprietary formats). Always verify with a hex editor before sharing highly sensitive files.

---

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
python3 -m pytest tests/ -v

# With coverage
python3 -m pytest tests/ --cov=trace --cov-report=term-missing
```

### Code Quality

```bash
# Format with black
black trace/ tests/

# Lint with flake8
flake8 trace/ tests/
```

### Project Structure

```
trace/
├── trace/
│   ├── __init__.py
│   ├── __main__.py          # python -m trace entry point
│   ├── cli.py               # CLI commands (scan, scrub, batch)
│   ├── scanner.py           # Metadata extraction (all formats)
│   ├── scrubber.py          # Metadata removal (all formats)
│   ├── web.py               # Flask web GUI
│   └── templates/
│       └── index.html       # Single-file SPA
├── tests/
│   ├── __init__.py
│   └── test_scanner.py      # Unit tests
├── .github/workflows/
│   └── ci.yml               # GitHub Actions CI
├── pyproject.toml           # Package config
├── README.md
├── LICENSE
└── install.sh               # One-line installer
```

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/amazing-feature`
3. Run tests: `pytest tests/ -v`
4. Format code: `black trace/ tests/`
5. Submit a PR with clear description

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

Built with:
- [piexif](https://github.com/hMatoba/piexif) — EXIF parsing
- [PyPDF2](https://github.com/py-pdf/PyPDF2) — PDF metadata
- [mutagen](https://github.com/quodlibet/mutagen) — Audio tags
- [Flask](https://flask.palletsprojects.com/) — Web framework

---

**Trace** — because your files shouldn't leak your life.

*Made for privacy advocates, journalists, activists, and anyone who values opsec.*