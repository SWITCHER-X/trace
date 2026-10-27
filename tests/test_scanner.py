"""
Unit tests for Trace - Metadata Scanner
"""

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

# Add parent directory to path so we can import trace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trace.scanner import scan_file, _is_risky, _assess_risk, ScanResult
from trace.scrubber import scrub_file


class TestScanner:
    """Test the metadata scanner."""

    def test_is_risky_gps(self):
        """GPS-related keys should be flagged as risky."""
        assert _is_risky("GPSLatitude", "37.7749") is True
        assert _is_risky("GPSLongitude", "-122.4194") is True
        assert _is_risky("GPSAltitude", "100") is True

    def test_is_risky_author(self):
        """Author/creator fields should be flagged as risky."""
        assert _is_risky("Author", "John Doe") is True
        assert _is_risky("Creator", "Jane Smith") is True
        assert _is_risky("Organization", "Acme Corp") is True

    def test_is_risky_camera(self):
        """Camera/device info should be flagged as risky."""
        assert _is_risky("Model", "iPhone 13") is True
        assert _is_risky("Make", "Apple") is True

    def test_is_risky_safe(self):
        """Non-identifying metadata should not be flagged."""
        assert _is_risky("Software", "Photoshop") is False
        assert _is_risky("DateTime", "2026:01:01 00:00:00") is False
        assert _is_risky("Width", "1920") is False

    def test_assess_risk_high(self):
        """Multiple risky items = HIGH risk."""
        metadata = {
            "GPSLatitude": "37.7749",
            "GPSLongitude": "-122.4194",
            "Author": "John Doe",
        }
        assert _assess_risk(metadata, []) == "high"

    def test_assess_risk_medium(self):
        """One risky item = MEDIUM risk."""
        metadata = {"Author": "John Doe"}
        assert _assess_risk(metadata, []) == "medium"

    def test_assess_risk_low(self):
        """Warnings only = LOW risk."""
        metadata = {"Software": "Photoshop"}
        warnings = ["GPS coordinates found"]
        assert _assess_risk(metadata, warnings) == "low"

    def test_assess_risk_none(self):
        """No risks = NONE."""
        metadata = {"Software": "Photoshop"}
        assert _assess_risk(metadata, []) == "none"


class TestScrubber:
    """Test the metadata scrubber."""

    def test_scrub_unsupported_type(self):
        """Unsupported file types should return an error."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"test")
            tmp_path = f.name
        try:
            result = scrub_file(tmp_path)
            assert result["status"] == "error"
            assert "Unsupported" in result.get("error", "")
        finally:
            os.unlink(tmp_path)

    def test_scrub_nonexistent_file(self):
        """Non-existent files should return an error."""
        result = scrub_file("/nonexistent/path/file.pdf")
        assert result["status"] == "error"

    def test_scan_nonexistent_file(self):
        """scan_file should handle missing files gracefully."""
        result = scan_file("/nonexistent/path/file.jpg")
        assert result.risk_level == "unknown"
        assert len(result.errors) > 0


def test_scan_pdf_metadata():
    """Integration test: scan a PDF with metadata."""
    import PyPDF2

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name

    try:
        writer = PyPDF2.PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_metadata({"/Author": "Test Author", "/Title": "Test Doc"})
        with open(tmp_path, "wb") as f_out:
            writer.write(f_out)

        result = scan_file(tmp_path)
        assert result.risk_level in ("medium", "high")
        assert "PDF:Author" in result.metadata
        assert result.metadata["PDF:Author"] == "Test Author"
    finally:
        os.unlink(tmp_path)


def test_scan_office_metadata():
    """Integration test: scan an Office document with metadata."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        tmp_path = f.name

    try:
        with zipfile.ZipFile(tmp_path, "w") as z:
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
            z.writestr(
                "docProps/core.xml",
                '<?xml version="1.0"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"><dc:creator>Test Author</dc:creator></cp:coreProperties>',
            )
            z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>')

        result = scan_file(tmp_path)
        assert result.risk_level in ("medium", "high")
        assert any("Author" in str(v) for v in result.metadata.values())
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
