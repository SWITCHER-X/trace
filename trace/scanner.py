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
# Audio scanners
# ---------------------------------------------------------------------------

def scan_mp3(path: str) -> ScanResult:
    """Extract ID3 metadata from MP3 files."""
    result = ScanResult(path)

    try:
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(path)
            if audio is not None:
                for key, val in audio.items():
                    if isinstance(val, list):
                        val = ", ".join(str(v) for v in val)
                    result.metadata[f"ID3:{key}"] = str(val)
        except ImportError:
            _scan_mp3_manual(path, result)
    except Exception as e:
        result.errors.append(f"Could not read MP3: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def _scan_mp3_manual(path: str, result: ScanResult) -> None:
    """Manual ID3v2 parser as fallback when mutagen is unavailable."""
    with open(path, "rb") as f:
        header = f.read(10)
        if header[:3] != b"ID3":
            result.warnings.append("No ID3v2 tag found")
            return

        major = header[3]
        minor = header[4]
        flags = header[5]
        size = _read_syncsafe_int(f.read(4))

        f.seek(10)
        end = 10 + size
        while f.tell() < end - 6:
            frame_header = f.read(10)
            if len(frame_header) < 10:
                break
            frame_id = frame_header[:4].decode("latin-1", errors="replace")
            frame_size = _read_syncsafe_int(frame_header[4:8])
            frame_flags = frame_header[8:10]

            frame_data = f.read(frame_size)
            if len(frame_data) < frame_size:
                break

            # Decode common frames
            if frame_id in ("TIT2", "TPE1", "TPE2", "TALB", "TYER", "TCON", "COMM", "TENC"):
                try:
                    # Skip encoding byte
                    text = frame_data[1:].decode("utf-8", errors="replace")
                    result.metadata[f"ID3:{frame_id}"] = text
                except Exception:
                    result.metadata[f"ID3:{frame_id}"] = f"<binary {len(frame_data)} bytes>"

def _read_syncsafe_int(data: bytes) -> int:
    """Read a 4-byte synchsafe integer."""
    val = 0
    for b in data:
        val = (val << 7) | (b & 0x7F)
    return val


def scan_wav(path: str) -> ScanResult:
    """Extract metadata from WAV files (RIFF chunks)."""
    result = ScanResult(path)

    try:
        with open(path, "rb") as f:
            riff = f.read(12)
            if riff[:4] != b"RIFF" or riff[8:12] != b"WAVE":
                result.warnings.append("Not a valid WAV file")
                result.risk_level = "low"
                return result

            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[:4].decode("latin-1", errors="replace")
                chunk_size = struct.unpack("<I", chunk_header[4:8])[0]

                if chunk_id == "LIST":
                    chunk_data = f.read(chunk_size)
                    # LIST chunk starts with "INFO" (4 bytes), then sub-chunks
                    pos = 4
                    while pos + 8 <= len(chunk_data):
                        sub_id = chunk_data[pos:pos+4].decode("latin-1", errors="replace")
                        sub_size = struct.unpack("<I", chunk_data[pos+4:pos+8])[0]
                        sub_data = chunk_data[pos+8:pos+8+sub_size]
                        try:
                            text = sub_data.decode("utf-8", errors="replace").strip("\x00")
                            if text:
                                result.metadata[f"WAV:{sub_id}"] = text
                        except Exception:
                            pass
                        pos += 8 + sub_size + (sub_size % 2)  # pad to even
                else:
                    f.seek(chunk_size, 1)

                if chunk_size % 2:
                    f.seek(1, 1)  # pad byte
    except Exception as e:
        result.errors.append(f"Could not read WAV: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def scan_flac(path: str) -> ScanResult:
    """Extract metadata from FLAC files (Vorbis comments in VORBIS_COMMENT block)."""
    result = ScanResult(path)

    try:
        with open(path, "rb") as f:
            header = f.read(4)
            if header != b"fLaC":
                result.warnings.append("Not a valid FLAC file")
                result.risk_level = "low"
                return result

            last_block = False
            while not last_block:
                block_header = f.read(4)
                if len(block_header) < 4:
                    break
                last_block = bool(block_header[0] & 0x80)
                block_type = block_header[0] & 0x7F
                block_size = int.from_bytes(block_header[1:4], "big")

                if block_type == 6:  # VORBIS_COMMENT
                    vendor_len = int.from_bytes(f.read(4), "little")
                    f.read(vendor_len)
                    comment_count = int.from_bytes(f.read(4), "little")
                    for _ in range(comment_count):
                        entry_len = int.from_bytes(f.read(4), "little")
                        entry = f.read(entry_len).decode("utf-8", errors="replace")
                        if "=" in entry:
                            key, val = entry.split("=", 1)
                            result.metadata[f"FLAC:{key}"] = val
                        else:
                            result.metadata[f"FLAC:{entry}"] = ""
                    break
                else:
                    f.seek(block_size, 1)
    except Exception as e:
        result.errors.append(f"Could not read FLAC: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def scan_m4a(path: str) -> ScanResult:
    """Extract metadata from M4A files (iTunes metadata atoms)."""
    result = ScanResult(path)

    try:
        with open(path, "rb") as f:
            while True:
                atom_header = f.read(8)
                if len(atom_header) < 8:
                    break
                atom_size = int.from_bytes(atom_header[:4], "big")
                atom_type = atom_header[4:8].decode("latin-1", errors="replace")

                if atom_type == "moov":
                    # QuickTime atom - look for 'nam', 'ART', 'alb', 'cprt', 'desc'
                    atom_data = f.read(atom_size - 8)
                    _parse_m4a_atoms(atom_data, result.metadata)
                elif atom_type == "mdta":
                    # iTunes metadata atom
                    atom_data = f.read(atom_size - 8)
                    _parse_itunes_atoms(atom_data, result.metadata)
                else:
                    f.seek(atom_size - 8, 1)
    except Exception as e:
        result.errors.append(f"Could not read M4A: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def _parse_m4a_atoms(data: bytes, metadata: dict) -> None:
    """Parse QuickTime metadata atoms."""
    pos = 0
    while pos + 8 <= len(data):
        atom_size = int.from_bytes(data[pos:pos+4], "big")
        atom_type = data[pos+4:pos+8].decode("latin-1", errors="replace")
        if atom_type == "name":
            # 'name' atom contains the title
            atom_content = data[pos+8:pos+atom_size]
            # Skip version/flags (4 bytes) and language (2 bytes)
            if len(atom_content) > 10:
                result.metadata["M4A:Title"] = atom_content[10:].decode("utf-8", errors="replace").strip("\x00")
        pos += atom_size


def _parse_itunes_atoms(data: bytes, metadata: dict) -> None:
    """Parse iTunes metadata atoms."""
    pos = 0
    while pos + 8 <= len(data):
        atom_size = int.from_bytes(data[pos:pos+4], "big")
        atom_type = data[pos+4:pos+8].decode("latin-1", errors="replace")
        atom_content = data[pos+8:pos+atom_size]

        if atom_type == "----":
            # User-defined metadata
            inner_pos = 8  # Skip version/flags
            while inner_pos + 8 <= len(atom_content):
                inner_size = int.from_bytes(atom_content[inner_pos:inner_pos+4], "big")
                inner_type = atom_content[inner_pos+4:inner_pos+8].decode("latin-1", errors="replace")
                inner_content = atom_content[inner_pos+8:inner_pos+inner_size]
                # Skip name and data (4 bytes each)
                if len(inner_content) > 8:
                    name = inner_content[:4].decode("latin-1", errors="replace")
                    value = inner_content[8:]
                    try:
                        text = value.decode("utf-8", errors="replace").strip("\x00")
                        if text:
                            result.metadata[f"iTunes:{name}"] = text
                    except Exception:
                        pass
                inner_pos += inner_size
        pos += atom_size


def scan_ogg(path: str) -> ScanResult:
    """Extract metadata from OGG files (Vorbis comments)."""
    result = ScanResult(path)

    try:
        with open(path, "rb") as f:
            header = f.read(7)
            if header != b"\x01vorbis":
                result.warnings.append("Not a valid OGG/Vorbis file")
                result.risk_level = "low"
                return result

            # Skip version header
            f.read(7)
            # Skip comment header type (1 byte)
            comment_header = f.read(1)
            if comment_header != b"\x03":
                result.warnings.append("Not a Vorbis comment header")
                result.risk_level = "low"
                return result

            vendor_len = int.from_bytes(f.read(4), "little")
            f.read(vendor_len)
            comment_count = int.from_bytes(f.read(4), "little")

            for _ in range(comment_count):
                entry_len = int.from_bytes(f.read(4), "little")
                entry = f.read(entry_len).decode("utf-8", errors="replace")
                if "=" in entry:
                    key, val = entry.split("=", 1)
                    result.metadata[f"OGG:{key}"] = val
    except Exception as e:
        result.errors.append(f"Could not read OGG: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


# ---------------------------------------------------------------------------
# Video scanners
# ---------------------------------------------------------------------------

def scan_mp4(path: str) -> ScanResult:
    """Extract metadata from MP4 files (QuickTime atoms)."""
    result = ScanResult(path)

    try:
        with open(path, "rb") as f:
            while True:
                atom_header = f.read(8)
                if len(atom_header) < 8:
                    break
                atom_size = int.from_bytes(atom_header[:4], "big")
                atom_type = atom_header[4:8].decode("latin-1", errors="replace")

                if atom_type == "moov":
                    atom_data = f.read(atom_size - 8)
                    _parse_qt_atoms(atom_data, result.metadata)
                elif atom_type == "udta":
                    atom_data = f.read(atom_size - 8)
                    _parse_qt_atoms(atom_data, result.metadata)
                else:
                    f.seek(atom_size - 8, 1)
    except Exception as e:
        result.errors.append(f"Could not read MP4: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def _parse_qt_atoms(data: bytes, metadata: dict) -> None:
    """Parse QuickTime metadata atoms."""
    pos = 0
    while pos + 8 <= len(data):
        atom_size = int.from_bytes(data[pos:pos+4], "big")
        atom_type = data[pos+4:pos+8].decode("latin-1", errors="replace")

        if atom_type in ("name", "©nam", "©ART", "©alb", "©cprt", "©desc"):
            atom_content = data[pos+8:pos+atom_size]
            if len(atom_content) > 8:
                text = atom_content[8:].decode("utf-8", errors="replace").strip("\x00")
                if text:
                    metadata[f"MP4:{atom_type}"] = text

        pos += atom_size


def scan_text(path: str) -> ScanResult:
    """Extract metadata from text files (first lines, shebang, embedded PII)."""
    import re

    result = ScanResult(path)

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[:20]  # First 20 lines only
    except Exception as e:
        result.errors.append(f"Could not read text file: {e}")
        result.risk_level = "unknown"
        return result

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Shebang line
        if i == 0 and line_stripped.startswith("#!"):
            result.metadata["Text:Shebang"] = line_stripped

        # Common metadata patterns
        for pattern, label in [
            (r"^#\s*Author:\s*(.+)$", "Author"),
            (r"^#\s*Created:\s*(.+)$", "Created"),
            (r"^#\s*Copyright:\s*(.+)$", "Copyright"),
            (r"^#\s*Email:\s*(.+)$", "Email"),
            (r"^#\s*Maintainer:\s*(.+)$", "Maintainer"),
        ]:
            m = re.match(pattern, line_stripped, re.IGNORECASE)
            if m:
                result.metadata[f"Text:{label}"] = m.group(1).strip()

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


def scan_zip(path: str) -> ScanResult:
    """Extract metadata from ZIP files (comment field, file timestamps)."""
    result = ScanResult(path)

    try:
        with zipfile.ZipFile(path) as z:
            comment = z.comment
            if comment:
                try:
                    result.metadata["Zip:Comment"] = comment.decode("utf-8", errors="replace")
                except Exception:
                    result.metadata["Zip:Comment"] = f"<binary {len(comment)} bytes>"

            for info in z.infolist()[:20]:
                dt = info.date_time
                result.metadata[f"Zip:File:{info.filename}"] = f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d} {dt[3]:02d}:{dt[4]:02d}:{dt[5]:02d}"

    except zipfile.BadZipFile:
        result.errors.append("Not a valid ZIP file")
        result.risk_level = "unknown"
        return result
    except Exception as e:
        result.errors.append(f"Could not read ZIP: {e}")
        result.risk_level = "unknown"
        return result

    result.risk_level = _assess_risk(result.metadata, result.warnings)
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}
PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".py", ".log", ".json", ".yaml", ".yml"}
ARCHIVE_EXTENSIONS = {".zip"}


def scan_file(path: str) -> ScanResult:
    """Dispatch to the correct format scanner based on file extension."""
    ext = os.path.splitext(path)[1].lower()

    if ext in IMAGE_EXTENSIONS:
        return scan_jpeg_png(path)
    if ext in PDF_EXTENSIONS:
        return scan_pdf(path)
    if ext in OFFICE_EXTENSIONS:
        return scan_office(path)
    if ext in AUDIO_EXTENSIONS:
        return scan_audio(path)
    if ext in VIDEO_EXTENSIONS:
        return scan_video(path)
    if ext in TEXT_EXTENSIONS:
        return scan_text(path)
    if ext in ARCHIVE_EXTENSIONS:
        return scan_zip(path)

    result = ScanResult(path)
    result.warnings.append(f"Unsupported file type: {ext}")
    result.risk_level = "unknown"
    return result


def scan_audio(path: str) -> ScanResult:
    """Route to the correct audio scanner based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        return scan_mp3(path)
    if ext == ".wav":
        return scan_wav(path)
    if ext == ".flac":
        return scan_flac(path)
    if ext == ".m4a":
        return scan_m4a(path)
    if ext == ".ogg":
        return scan_ogg(path)
    result = ScanResult(path)
    result.warnings.append(f"Unsupported audio type: {ext}")
    result.risk_level = "unknown"
    return result


def scan_video(path: str) -> ScanResult:
    """Route to the correct video scanner based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".mp4", ".mov", ".mkv"):
        return scan_mp4(path)
    if ext == ".avi":
        result = ScanResult(path)
        result.warnings.append("AVI support not yet implemented")
        result.risk_level = "low"
        return result
    result = ScanResult(path)
    result.warnings.append(f"Unsupported video type: {ext}")
    result.risk_level = "unknown"
    return result


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
