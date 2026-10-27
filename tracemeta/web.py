"""
Trace Web GUI - Flask-based drag-and-drop metadata inspector
Run: python -m trace.web
Then open: http://localhost:5001
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file, g

from .scanner import scan_file
from .scrubber import scrub_file

# ─── Configuration ────────────────────────────────────────────────────────
class Config:
    """Application configuration from environment variables."""
    
    # Security
    SECRET_KEY: str = os.environ.get("TRACE_SECRET_KEY", secrets.token_hex(32))
    SESSION_COOKIE_SECURE: bool = os.environ.get("TRACE_HTTPS", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    PERMANENT_SESSION_LIFETIME: int = 3600  # 1 hour
    
    # Rate limiting
    RATELIMIT_ENABLED: bool = os.environ.get("TRACE_RATELIMIT", "true").lower() == "true"
    RATELIMIT_DEFAULT: str = "100 per hour"
    RATELIMIT_STORAGE_URL: str = "memory://"
    
    # CORS
    CORS_ORIGINS: list[str] = os.environ.get("TRACE_CORS_ORIGINS", "http://localhost:5001,http://127.0.0.1:5001").split(",")
    
    # File upload
    MAX_CONTENT_LENGTH: int = 50 * 1024 * 1024  # 50 MB
    ALLOWED_EXTENSIONS: set[str] = {
        # Images
        ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp",
        # Documents
        ".pdf",
        # Office
        ".docx", ".xlsx", ".pptx",
        # Audio
        ".mp3", ".wav", ".flac", ".m4a", ".ogg",
        # Video
        ".mp4", ".mov", ".mkv", ".avi",
        # Text
        ".txt", ".md", ".csv", ".py", ".log", ".json", ".yaml", ".yml",
        # Archive
        ".zip",
    }
    MAX_FILENAME_LENGTH: int = 255
    
    # Security headers
    CSP_POLICY: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    
    # Debug
    DEBUG: bool = os.environ.get("TRACE_DEBUG", "false").lower() == "true"
    TESTING: bool = False

# ─── App Factory ──────────────────────────────────────────────────────────
def create_app(config_class: type = Config) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)
    
    # ─── Security Headers ────────────────────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses."""
        # Content Security Policy
        response.headers["Content-Security-Policy"] = app.config["CSP_POLICY"]
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions policy
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        
        # HSTS (only if HTTPS)
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Remove server header
        response.headers.pop("Server", None)
        
        return response
    
    # ─── CORS ────────────────────────────────────────────────────────────
    @app.after_request
    def add_cors_headers(response):
        """Add CORS headers for allowed origins."""
        origin = request.headers.get("Origin")
        if origin and origin in app.config["CORS_ORIGINS"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "3600"
        return response
    
    @app.route("/", methods=["OPTIONS"])
    @app.route("/api/<path:path>", methods=["OPTIONS"])
    def cors_preflight(path=None):
        """Handle CORS preflight requests."""
        return "", 204
    
    # ─── Rate Limiting ───────────────────────────────────────────────────
    # Simple in-memory rate limiter
    _rate_limit_store: dict[str, list[float]] = {}
    
    def check_rate_limit(key: str, limit: int = 100, window: int = 3600) -> tuple[bool, int]:
        """Check if request is within rate limit. Returns (allowed, remaining)."""
        now = time.time()
        if key not in _rate_limit_store:
            _rate_limit_store[key] = []
        
        # Clean old entries
        _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]
        
        if len(_rate_limit_store[key]) >= limit:
            return False, 0
        
        _rate_limit_store[key].append(now)
        return True, limit - len(_rate_limit_store[key])
    
    def rate_limit(f):
        """Decorator for rate limiting endpoints."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if not app.config["RATELIMIT_ENABLED"]:
                return f(*args, **kwargs)
            
            # Use IP + endpoint as key
            key = f"{request.remote_addr}:{request.endpoint}"
            allowed, remaining = check_rate_limit(key, limit=100, window=3600)
            
            if not allowed:
                return jsonify({
                    "error": "Rate limit exceeded. Try again later.",
                    "retry_after": 3600
                }), 429
            
            response = f(*args, **kwargs)
            # Add rate limit headers
            if isinstance(response, tuple):
                resp_obj = response[0]
            else:
                resp_obj = response
            if hasattr(resp_obj, "headers"):
                resp_obj.headers["X-RateLimit-Remaining"] = str(remaining)
                resp_obj.headers["X-RateLimit-Limit"] = "100"
            return response
        return decorated
    
    # ─── Input Validation & Sanitization ────────────────────────────────
    def validate_filename(filename: str) -> tuple[bool, str]:
        """Validate and sanitize filename."""
        if not filename or filename.strip() == "":
            return False, "Empty filename"
        
        # Remove path traversal attempts
        filename = os.path.basename(filename)
        filename = filename.replace("..", "").replace("/", "").replace("\\", "")
        
        # Check length
        if len(filename) > app.config["MAX_FILENAME_LENGTH"]:
            return False, f"Filename too long (max {app.config['MAX_FILENAME_LENGTH']} chars)"
        
        # Check extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in app.config["ALLOWED_EXTENSIONS"]:
            return False, f"File type not allowed: {ext}"
        
        # Check for dangerous patterns
        dangerous = ["\x00", "|", ";", "&", "$", "`", ">", "<"]
        if any(d in filename for d in dangerous):
            return False, "Filename contains invalid characters"
        
        return True, filename
    
    def sanitize_error_message(error: Exception) -> str:
        """Sanitize error messages to prevent information leakage."""
        # In production, return generic messages
        if not app.config["DEBUG"]:
            return "An error occurred. Please try again."
        return str(error)
    
    # ─── Request Validation ──────────────────────────────────────────────
    @app.before_request
    def validate_request():
        """Validate incoming requests."""
        # Enforce content length
        if request.content_length and request.content_length > app.config["MAX_CONTENT_LENGTH"]:
            return jsonify({"error": "File too large (max 50 MB)"}), 413
        
        # Block suspicious user agents (basic bot protection)
        ua = request.headers.get("User-Agent", "").lower()
        suspicious = ["sqlmap", "nikto", "nmap", "masscan", "zap", "burp", "dirb", "gobuster"]
        if any(s in ua for s in suspicious):
            return jsonify({"error": "Access denied"}), 403
    
    # ─── In-Memory Scan Cache with TTL ──────────────────────────────────
    scan_cache: dict[str, dict] = {}
    CACHE_TTL = 300  # 5 minutes
    
    def cleanup_cache():
        """Remove expired cache entries."""
        now = time.time()
        expired = [
            k for k, v in scan_cache.items()
            if now - v.get("_cached_at", 0) > CACHE_TTL
        ]
        for k in expired:
            scan_cache.pop(k, None)
    
    # ─── Routes ──────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        """Serve the main web interface."""
        cleanup_cache()
        return render_template("index.html")
    
    @app.route("/health")
    def health():
        """Health check endpoint (no auth required)."""
        return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})
    
    @app.route("/api/scan", methods=["POST"])
    @rate_limit
    def api_scan():
        """Scan an uploaded file for metadata."""
        cleanup_cache()
        
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
        
        # Validate filename
        valid, result = validate_filename(file.filename)
        if not valid:
            return jsonify({"error": result}), 400
        safe_filename = result
        
        # Save uploaded file to temp location
        ext = os.path.splitext(safe_filename)[1]
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=ext, prefix="trace_scan_"
            ) as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name
        except Exception as e:
            return jsonify({"error": sanitize_error_message(e)}), 500
        
        try:
            result = scan_file(tmp_path)
            result_dict = result.to_dict()
            
            # Cache result for potential scrub (with timestamp)
            result_dict["_cached_at"] = time.time()
            scan_cache[result_dict["filename"]] = result_dict
            
            # Remove internal fields from response
            result_dict.pop("_cached_at", None)
            
            return jsonify(result_dict)
        except Exception as e:
            return jsonify({"error": sanitize_error_message(e)}), 500
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    
    @app.route("/api/scrub", methods=["POST"])
    @rate_limit
    def api_scrub():
        """Scrub metadata from an uploaded file and return the clean copy."""
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
        
        # Validate filename
        valid, result = validate_filename(file.filename)
        if not valid:
            return jsonify({"error": result}), 400
        safe_filename = result
        
        # Save uploaded file to temp location
        ext = os.path.splitext(safe_filename)[1]
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=ext, prefix="trace_scrub_"
            ) as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name
        except Exception as e:
            return jsonify({"error": sanitize_error_message(e)}), 500
        
        try:
            result = scrub_file(tmp_path)
            
            if result["status"] == "error":
                return jsonify({
                    "error": sanitize_error_message(Exception(result.get("error", "Unknown error")))
                }), 500
            
            # Verify output file exists and is safe
            output_path = result["output"]
            if not os.path.exists(output_path):
                return jsonify({"error": "Scrub failed: output file not created"}), 500
            
            # Sanitize download filename
            download_name = os.path.basename(output_path)
            download_name = re.sub(r"[^\w\-\.]", "_", download_name)
            
            # Return the clean file as download
            return send_file(
                output_path,
                as_attachment=True,
                download_name=download_name,
                mimetype="application/octet-stream",
            )
        except Exception as e:
            return jsonify({"error": sanitize_error_message(e)}), 500
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    
    @app.route("/api/batch", methods=["POST"])
    @rate_limit
    def api_batch():
        """Scan all uploaded files in a batch."""
        cleanup_cache()
        
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400
        
        files = request.files.getlist("files")
        if len(files) > 50:  # Limit batch size
            return jsonify({"error": "Too many files (max 50)"}), 400
        
        results = []
        
        for file in files:
            if file.filename == "":
                continue
            
            # Validate filename
            valid, safe_filename = validate_filename(file.filename)
            if not valid:
                results.append({
                    "filename": file.filename,
                    "error": safe_filename,
                    "risk_level": "unknown",
                })
                continue
            
            ext = os.path.splitext(safe_filename)[1]
            try:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=ext, prefix="trace_batch_"
                ) as tmp:
                    file.save(tmp.name)
                    tmp_path = tmp.name
            except Exception as e:
                results.append({
                    "filename": file.filename,
                    "error": sanitize_error_message(e),
                    "risk_level": "unknown",
                })
                continue
            
            try:
                result = scan_file(tmp_path)
                results.append(result.to_dict())
            except Exception as e:
                results.append({
                    "filename": file.filename,
                    "error": sanitize_error_message(e),
                    "risk_level": "unknown",
                })
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        
        risky_count = sum(
            1 for r in results if r.get("risk_level") in ("high", "medium")
        )
        
        return jsonify({
            "total": len(results),
            "risky": risky_count,
            "results": results,
        })
    
    # ─── Error Handlers ──────────────────────────────────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request"}), 400
    
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404
    
    @app.errorhandler(413)
    def request_entity_too_large(e):
        return jsonify({"error": "File too large (max 50 MB)"}), 413
    
    @app.errorhandler(429)
    def ratelimit_exceeded(e):
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Internal server error"}), 500
    
    return app


# ─── Entry Point ──────────────────────────────────────────────────────────
def main():
    """Run the web GUI."""
    app = create_app()
    print("=" * 60)
    print("  Trace Web GUI")
    print("  Open: http://localhost:5001")
    print("  Debug mode: OFF")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=False)


if __name__ == "__main__":
    main()