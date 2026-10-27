# Trace

**Universal File Metadata & Privacy Inspector**

Drag and drop any file — see exactly what hidden data it contains, and scrub it with one click. Runs on Windows, Mac, Linux, and Termux (Android). Everything happens locally. No uploads. No network.

```
┌─────────────────────────────────────────────────────────────┐
│  trace scan photo.jpg                                       │
│                                                             │
│  File:    photo.jpg                                         │
│  Size:    2.4 MB                                            │
│  Risk:    HIGH                                              │
│                                                             │
│  [WARNINGS]                                                 │
│  * GPS coordinates found — photo location can be determined │
│                                                             │
│  [METADATA FOUND]                                           │
│  EXIF:GPSLatitude: 37.7749° N  <-- RISKY                    │
│  EXIF:GPSLongitude: -122.4194° W  <-- RISKY                 │
│  EXIF:Model: iPhone 13                                      │
│  EXIF:DateTime: 2026-03-15 14:32:10                         │
└─────────────────────────────────────────────────────────────┘
```

## The Problem

Every photo, PDF, and document you share carries hidden metadata: GPS coordinates, device serial numbers, software versions, timestamps, author names. People doxx themselves constantly without realizing it. Existing tools are command-line only, Windows-only, or require uploading your files to sketchy websites.

Trace fixes that. One command. Local only. Cross-platform.

## Features

| Feature | What it catches |
|---------|-----------------|
| **EXIF scanner** | GPS coordinates, camera model, serial number, timestamps from photos |
| **Document inspector** | Author name, company, template path, revision history in PDFs/Office docs |
| **Video metadata** | Device info, creation software in MP4/MOV |
| **Risk scoring** | High/Medium/Low/None based on personal identifier detection |
| **One-click scrub** | Strips identifying metadata before you share (Phase 2) |
| **Batch mode** | Scan entire folders before uploading to social media |
| **JSON output** | Machine-readable for scripting and pipelines |

## Install

```bash
pip install trace-metadata
```

Or from source:

```bash
git clone https://github.com/your-username/trace.git
cd trace
pip install -e .
```

## Usage

```bash
# Scan a single file
trace scan photo.jpg

# JSON output (for scripts)
trace scan photo.jpg --json

# Scan an entire folder
trace batch ./downloads/

# Scan and strip metadata (coming in Phase 2)
trace scrub photo.jpg
```

## Supported Formats

- **Images:** JPEG, PNG, TIFF, WebP (EXIF)
- **Documents:** PDF
- **Office:** .docx, .xlsx, .pptx (Office Open XML)

## Privacy

Trace runs 100% locally. No files are uploaded. No network connections are made. Your data never leaves your machine.

## License

MIT

## Disclaimer

Trace is a privacy aid, not a guarantee of anonymity. Some metadata may be embedded in ways not detectable by this tool. Always verify before sharing sensitive files.
