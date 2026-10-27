"""
Trace - Universal File Metadata & Privacy Inspector
Phase 1: Metadata scanner

Scans images, PDFs, and Office documents for embedded metadata that
could reveal your identity, location, or device information.

Everything runs locally. No uploads. No network.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class ScanResult:
    """Container for metadata findings from a single file."""

    def __init__(self, path: str):
        self.path = str(path)
        self.filename = os.path.basename(path)
        self.size = os.path.getsize(path) if os.path.exists(path) else 0
        self.metadata: dict[str, Any] = {}
        self.risk_level = "none"
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "filename": self.filename,
            "size": self.size,
            "metadata": self.metadata,
            "risk_level": self.risk_level,
            "warnings": self.warnings,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_risky(key: str, value: Any) -> bool:
    """Heuristic: flag values that look like personal identifiers or locations."""
    if value is None:
        return False
    s = str(value).lower()
    risky_keywords = [
        "gps", "latitude", "longitude", "altitude",
        "author", "creator", "last modified by",
        "company", "organization",
        "serial", "camera", "lens",
        "email",
        "address",
    ]
    risky_keys = [
        "gps", "latitude", "longitude", "altitude",
        "author", "creator", "lastmodifiedby",
        "company", "organization",
        "cameraserial", "lensserial",
        "artist", "copyright",
    ]
    k = key.lower()
    if any(rk in k for rk in risky_keys):
        return True
    if any(rk in s for rk in ["@", "http", "gps", "n ", "e ", "degree"]):
        return True
    return False


def _assess_risk(metadata: dict[str, Any], warnings: list[str]) -> str:
    """Return 'high', 'medium', 'low', or 'none'."""
    risky = sum(1 for k, v in metadata.items() if _is_risky(k, v))
    if risky >= 3:
        return "high"
    if risky >= 1:
        return "medium"
    if warnings:
        return "low"
    return "none"


# ---------------------------------------------------------------------------
# Format scanners
# ---------------------------------------------------------------------------


def scan_jpeg_png(path: str) -> ScanResult:
    """Extract EXIF metadata from JPEG and PNG files."""
    result = ScanResult(path)

    try:
        import piexif  # type: ignore
    except ImportError:
        result.errors.append("piexif not installed — install with: pip install piexif")
        result.risk_level = "unknown"
        return result

    try:
        exif_dict = piexif.load(path)
    except Exception as e:
        result.errors.append(f"Could not read EXIF: {e}")
        result.risk_level = "unknown"
        return result

    # Flatten all IFD sections into one dict
    for ifd_name in ("0th", "Exif", "GPS", "1st", "thumbnail"):
        ifd = exif_dict.get(ifd_name) or {}
        for tag, val in ifd.items():
            try:
                decoded = piexif.TAGS.get(ifd_name, {}).get(tag, {}).get("Name", str(tag))
            except Exception:
                decoded = str(tag)
            if isinstance(val, bytes):
                try:
                    val = val.decode("utf-8", errors="replace")
                except Exception:
                    val = f"<binary {len(val)} bytes>"
            result.metadata[f"EXIF:{decoded}"] = val

    # GPS specific check
    gps = exif_dict.get("GPS", {})
    if gps:
        result.warnings.append("GPS coordinates found — photo location can be determined")

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def scan_pdf(path: str) -> ScanResult:
    """Extract metadata from PDF files."""
    result = ScanResult(path)

    try:
        import PyPDF2  # type: ignore
    except ImportError:
        result.errors.append("PyPDF2 not installed — install with: pip install PyPDF2")
        result.risk_level = "unknown"
        return result

    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            meta = reader.metadata or {}
            for key, val in meta.items():
                clean_key = key.lstrip("/")
                result.metadata[f"PDF:{clean_key}"] = str(val)
    except Exception as e:
        result.errors.append(f"Could not read PDF: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def scan_office(path: str) -> ScanResult:
    """Extract core properties from Office Open XML documents (.docx, .xlsx, .pptx)."""
    result = ScanResult(path)

    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            core = None
            for n in names:
                if n.endswith("docProps/core.xml"):
                    core = n
                    break
                if n.endswith("docProps/app.xml"):
                    # fallback if core.xml missing
                    if core is None:
                        core = n

            if core is None:
                result.warnings.append("No document properties found")
                result.risk_level = "low"
                return result

            xml = z.read(core).decode("utf-8", errors="replace")

    except zipfile.BadZipFile:
        result.errors.append("Not a valid Office document (bad ZIP)")
        result.risk_level = "unknown"
        return result
    except Exception as e:
        result.errors.append(f"Could not read Office file: {e}")
        result.risk_level = "unknown"
        return result

    # Simple XML tag extraction (avoid lxml dependency)
    import re

    tags = re.findall(r"<([a-zA-Z0-9:]+)>([^<]*)</\1>", xml)
    for tag, val in tags:
        clean_tag = tag.split(":")[-1] if ":" in tag else tag
        if val.strip():
            result.metadata[f"Office:{clean_tag}"] = val.strip()

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}
PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}


def scan_file(path: str) -> ScanResult:
    """Dispatch to the correct format scanner based on file extension."""
    ext = os.path.splitext(path)[1].lower()

    if ext in IMAGE_EXTENSIONS:
        return scan_jpeg_png(path)
    if ext in PDF_EXTENSIONS:
        return scan_pdf(path)
    if ext in OFFICE_EXTENSIONS:
        return scan_office(path)

    result = ScanResult(path)
    result.warnings.append(f"Unsupported file type: {ext}")
    result.risk_level = "unknown"
    return result


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------


def print_result(result: ScanResult) -> None:
    """Human-readable terminal output."""
    print(f"\n{'='*60}")
    print(f"  File: {result.filename}")
    print(f"  Size: {result.size} bytes")
    print(f"  Risk: {result.risk_level.upper()}")
    print(f"{'='*60}")

    if result.errors:
        print("\n  [ERRORS]")
        for e in result.errors:
            print(f"    ! {e}")

    if result.warnings:
        print("\n  [WARNINGS]")
        for w in result.warnings:
            print(f"    * {w}")

    if result.metadata:
        print("\n  [METADATA FOUND]")
        for k, v in result.metadata.items():
            risky = " <-- RISKY" if _is_risky(k, v) else ""
            print(f"    {k}: {v}{risky}")
    else:
        print("\n  [NO METADATA FOUND]")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Trace - File metadata inspector")
    parser.add_argument("file", help="File to scan")
    args = parser.parse_args()

    res = scan_file(args.file)
    print_result(res)
    print(json.dumps(res.to_dict(), indent=2))
