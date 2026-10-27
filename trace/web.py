"""
Trace Web GUI - Flask-based drag-and-drop metadata inspector
Run: python -m trace.web
Then open: http://localhost:5000
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file

from .scanner import scan_file, print_result
from .scrubber import scrub_file

app = Flask(__name__, template_folder="templates", static_folder="static")

# In-memory storage for scan results (session-based, in production use Redis/DB)
scan_cache: dict[str, dict] = {}


@app.route("/")
def index():
    """Serve the main web interface."""
    return render_template("index.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scan an uploaded file for metadata."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=os.path.splitext(file.filename)[1]
    ) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = scan_file(tmp_path)
        result_dict = result.to_dict()

        # Cache result for potential scrub
        scan_cache[result_dict["filename"]] = result_dict

        return jsonify(result_dict)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.route("/api/scrub", methods=["POST"])
def api_scrub():
    """Scrub metadata from an uploaded file and return the clean copy."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=os.path.splitext(file.filename)[1]
    ) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = scrub_file(tmp_path)

        if result["status"] == "error":
            return jsonify({"error": result.get("error", "Unknown error")}), 500

        # Return the clean file as download
        return send_file(
            result["output"],
            as_attachment=True,
            download_name=os.path.basename(result["output"]),
            mimetype="application/octet-stream",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temp input file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.route("/api/batch", methods=["POST"])
def api_batch():
    """Scan all uploaded files in a batch."""
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    results = []

    for file in files:
        if file.filename == "":
            continue

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        try:
            result = scan_file(tmp_path)
            results.append(result.to_dict())
        except Exception as e:
            results.append(
                {
                    "filename": file.filename,
                    "error": str(e),
                    "risk_level": "unknown",
                }
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    risky_count = sum(
        1 for r in results if r.get("risk_level") in ("high", "medium")
    )

    return jsonify(
        {
            "total": len(results),
            "risky": risky_count,
            "results": results,
        }
    )


def main():
    """Run the web GUI."""
    print("=" * 60)
    print("  Trace Web GUI")
    print("  Open: http://localhost:5001")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=True)


if __name__ == "__main__":
    main()
