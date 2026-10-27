"""
Trace - Scrubber (Phase 2)
Strips metadata from files and creates clean copies.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Any


def scrub_image(path: str, output_path: str | None = None) -> dict[str, Any]:
    """Remove EXIF metadata from JPEG/PNG images."""
    import piexif

    path = str(path)
    if output_path is None:
        stem = Path(path).stem
        suffix = Path(path).suffix
        output_path = f"{stem}_clean{suffix}"

    try:
        piexif.remove(path, output_path)
        return {
            "input": path,
            "output": output_path,
            "status": "scrubbed",
            "metadata_removed": "EXIF",
        }
    except Exception as e:
        return {
            "input": path,
            "output": output_path,
            "status": "error",
            "error": str(e),
        }


def scrub_pdf(path: str, output_path: str | None = None) -> dict[str, Any]:
    """Remove metadata from PDF files."""
    from PyPDF2 import PdfReader, PdfWriter

    path = str(path)
    if output_path is None:
        stem = Path(path).stem
        suffix = Path(path).suffix
        output_path = f"{stem}_clean{suffix}"

    try:
        reader = PdfReader(path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # No metadata added = clean
        with open(output_path, "wb") as f:
            writer.write(f)

        return {
            "input": path,
            "output": output_path,
            "status": "scrubbed",
            "metadata_removed": "PDF metadata",
        }
    except Exception as e:
        return {
            "input": path,
            "output": output_path,
            "status": "error",
            "error": str(e),
        }


def scrub_office(path: str, output_path: str | None = None) -> dict[str, Any]:
    """Remove core properties from Office documents."""
    path = str(path)
    if output_path is None:
        stem = Path(path).stem
        suffix = Path(path).suffix
        output_path = f"{stem}_clean{suffix}"

    try:
        import shutil
        shutil.copy2(path, output_path)

        # Remove docProps/core.xml and docProps/app.xml from the ZIP
        with zipfile.ZipFile(output_path, "a") as z:
            names = z.namelist()
            to_remove = []
            for n in names:
                if n.endswith("docProps/core.xml") or n.endswith("docProps/app.xml"):
                    to_remove.append(n)
            # ZipFile doesn't support removal directly; recreate without those files
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            tmp.close()
            with zipfile.ZipFile(tmp.name, "w") as z_out:
                with zipfile.ZipFile(path) as z_in:
                    for item in z_in.infolist():
                        if item.filename not in to_remove:
                            data = z_in.read(item.filename)
                            z_out.writestr(item, data)
            os.replace(tmp.name, output_path)

        return {
            "input": path,
            "output": output_path,
            "status": "scrubbed",
            "metadata_removed": "Office core properties",
        }
    except Exception as e:
        return {
            "input": path,
            "output": output_path,
            "status": "error",
            "error": str(e),
        }


def scrub_file(path: str, output_path: str | None = None) -> dict[str, Any]:
    """Dispatch to the correct scrubber based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    image_exts = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}
    pdf_exts = {".pdf"}
    office_exts = {".docx", ".xlsx", ".pptx"}

    if ext in image_exts:
        return scrub_image(path, output_path)
    if ext in pdf_exts:
        return scrub_pdf(path, output_path)
    if ext in office_exts:
        return scrub_office(path, output_path)

    return {
        "input": path,
        "output": output_path,
        "status": "error",
        "error": f"Unsupported file type: {ext}",
    }
