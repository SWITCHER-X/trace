"""
Trace - Command Line Interface
Usage:
    trace scan <file>       Scan a file for metadata
    trace scrub <file>      Strip metadata from a file (creates clean copy)
    trace batch <dir>       Scan all files in a directory
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .scanner import scan_file, print_result
from .scrubber import scrub_file


def cmd_scan(path: str, json_out: bool = False) -> int:
    """Scan a single file."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        return 1

    result = scan_file(str(p))
    if json_out:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print_result(result)
    return 0


def cmd_batch(directory: str, json_out: bool = False) -> int:
    """Scan all files in a directory recursively."""
    d = Path(directory)
    if not d.is_dir():
        print(f"Error: Not a directory: {directory}", file=sys.stderr)
        return 1

    files = [f for f in d.rglob("*") if f.is_file()]
    if not files:
        print(f"No files found in {directory}")
        return 0

    results = []
    for f in sorted(files):
        result = scan_file(str(f))
        results.append(result.to_dict())
        if not json_out:
            print_result(result)

    if json_out:
        print(json.dumps(results, indent=2))

    # Summary
    risky = sum(1 for r in results if r["risk_level"] in ("high", "medium"))
    print(f"\nScanned {len(results)} files, {risky} with risky metadata.")
    return 0


def cmd_scrub(path: str) -> int:
    """Strip metadata from a file and create a clean copy."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        return 1

    result = scrub_file(str(p))
    if result["status"] == "scrubbed":
        print(f"✅ Scrubbed: {result['input']}")
        print(f"   Clean copy: {result['output']}")
        print(f"   Removed: {result['metadata_removed']}")
        return 0
    else:
        print(f"❌ Scrub failed: {result.get('error', 'unknown error')}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    argv = argv if argv is not None else sys.argv[1:]

    if not argv:
        print("Trace - Universal File Metadata & Privacy Inspector")
        print("Usage: trace <scan|scrub|batch> <path> [--json]")
        return 1

    command = argv[0]
    args = argv[1:]

    json_out = False
    if "--json" in args:
        json_out = True
        args.remove("--json")

    if not args:
        print("Error: Missing file path", file=sys.stderr)
        return 1

    path = args[0]

    if command == "scan":
        return cmd_scan(path, json_out=json_out)
    if command == "batch":
        return cmd_batch(path, json_out=json_out)
    if command == "scrub":
        return cmd_scrub(path)

    print(f"Error: Unknown command '{command}'", file=sys.stderr)
    print("Available commands: scan, scrub, batch")
    return 1


if __name__ == "__main__":
    sys.exit(main())
