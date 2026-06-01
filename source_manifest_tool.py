#!/usr/bin/env python3
"""Generate/update a Markdown manifest table for source files.

Columns:
- filename
- version
- modified_date
- modified_datetime
- checksum_crc32
- line_count
- file_size_bytes
- description

Versioning rule:
- New file: 1.0
- Existing file, checksum changed: +0.1 (e.g. 1.0 -> 1.1)
- Existing file, checksum unchanged: keep version
"""

from __future__ import annotations

import argparse
import binascii
import fnmatch
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

HEADERS = [
    "filename",
    "version",
    "modified_date",
    "modified_datetime",
    "checksum_crc32",
    "line_count",
    "file_size_bytes",
    "description",
]


@dataclass
class Row:
    filename: str
    version: str
    modified_date: str
    modified_datetime: str
    checksum_crc32: str
    line_count: int
    file_size_bytes: int
    description: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".", help="Root directory to scan")
    p.add_argument("--manifest", default="SOURCE_MANIFEST.md", help="Manifest markdown file path")
    p.add_argument(
        "--include",
        action="append",
        default=["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.java", "*.go", "*.rs", "*.c", "*.cpp", "*.h", "*.hpp", "*.cs", "*.kt", "*.swift", "*.php", "*.rb", "*.sh", "*.sql", "*.yaml", "*.yml", "*.json", "*.md"],
        help="Glob include pattern (can be repeated)",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[".git/*", "node_modules/*", "dist/*", "build/*", "venv/*", "__pycache__/*"],
        help="Glob exclude pattern (can be repeated)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print result to stdout only")
    p.add_argument(
        "--sync-mtime-from-manifest",
        action="store_true",
        help="When checksum is unchanged but modified_datetime differs, set file mtime to manifest datetime",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Verify files against checksum_crc32 values in manifest (like md5sum -c)",
    )
    return p.parse_args()


def crc32_checksum(path: Path) -> str:
    crc = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            crc = binascii.crc32(chunk, crc)
    return f"0x{crc & 0xFFFFFFFF:08X}"


def line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except UnicodeDecodeError:
        return 0


def to_modified_date(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts).strftime("%Y.%m.%d")


def to_modified_datetime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts).strftime("%Y.%m.%d %H:%M:%S")


def set_mtime_from_datetime(path: Path, datetime_text: str) -> bool:
    try:
        dt = datetime.strptime(datetime_text, "%Y.%m.%d %H:%M:%S")
        timestamp = dt.timestamp()
        os.utime(path, (timestamp, timestamp))
    except (ValueError, OSError):
        return False
    return True


def normalize_version(version: str) -> str:
    try:
        parts = [int(x) for x in version.split(".")]
    except Exception:
        return "1.0"

    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return f"{parts[0]}.0"


def bump_minor(version: str) -> str:
    normalized = normalize_version(version)
    major, minor = [int(x) for x in normalized.split(".")]
    return f"{major}.{minor + 1}"


def is_included(rel: str, includes: Iterable[str], excludes: Iterable[str]) -> bool:
    if any(fnmatch.fnmatch(rel, pat) for pat in excludes):
        return False
    return any(fnmatch.fnmatch(rel, pat) for pat in includes)


def parse_manifest(path: Path) -> Dict[str, Row]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: Dict[str, Row] = {}
    for ln in lines:
        if not ln.startswith("|"):
            continue
        parts = [x.strip() for x in ln.strip().strip("|").split("|")]
        if parts[0] in ("filename", "---"):
            continue
        try:
            if len(parts) == 8:
                rows[parts[0]] = Row(
                    filename=parts[0],
                    version=parts[1],
                    modified_date=parts[2],
                    modified_datetime=parts[3],
                    checksum_crc32=parts[4],
                    line_count=int(parts[5]),
                    file_size_bytes=int(parts[6]),
                    description=parts[7],
                )
            elif len(parts) == 7:
                rows[parts[0]] = Row(
                    filename=parts[0],
                    version=parts[1],
                    modified_date=parts[2],
                    modified_datetime=f"{parts[2]} 00:00:00",
                    checksum_crc32=parts[3],
                    line_count=int(parts[4]),
                    file_size_bytes=int(parts[5]),
                    description=parts[6],
                )
        except ValueError:
            continue
    return rows


def collect_files(root: Path, includes: Iterable[str], excludes: Iterable[str], manifest_path: Path) -> List[Path]:
    result: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel == manifest_path.name:
            continue
        if is_included(rel, includes, excludes):
            result.append(p)
    return sorted(result, key=lambda x: x.relative_to(root).as_posix())


def build_rows(
    root: Path,
    files: List[Path],
    prev: Dict[str, Row],
    sync_mtime_from_manifest: bool,
) -> tuple[List[Row], List[str], List[str]]:
    out: List[Row] = []
    mismatched_datetimes: List[str] = []
    synced_datetimes: List[str] = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        chk = crc32_checksum(f)
        lc = line_count(f)
        size = f.stat().st_size
        modified_date = to_modified_date(f)
        modified_datetime = to_modified_datetime(f)
        old: Optional[Row] = prev.get(rel)

        if old is None:
            version = "1.0"
            desc = ""
        else:
            normalized_version = normalize_version(old.version)
            checksum_unchanged = old.checksum_crc32 == chk
            version = normalized_version if checksum_unchanged else bump_minor(normalized_version)
            desc = old.description
            if checksum_unchanged and old.modified_datetime != modified_datetime:
                mismatched_datetimes.append(rel)
                if sync_mtime_from_manifest and set_mtime_from_datetime(f, old.modified_datetime):
                    modified_date = old.modified_date
                    modified_datetime = old.modified_datetime
                    synced_datetimes.append(rel)

        out.append(
            Row(
                filename=rel,
                version=version,
                modified_date=modified_date,
                modified_datetime=modified_datetime,
                checksum_crc32=chk,
                line_count=lc,
                file_size_bytes=size,
                description=desc,
            )
        )
    return out, mismatched_datetimes, synced_datetimes


def render_markdown(rows: List[Row]) -> str:
    header = "| " + " | ".join(HEADERS) + " |"
    sep = "|" + "|".join(["---"] * len(HEADERS)) + "|"
    body = [
        "| "
        + " | ".join(
            [
                r.filename,
                r.version,
                r.modified_date,
                r.modified_datetime,
                r.checksum_crc32,
                str(r.line_count),
                str(r.file_size_bytes),
                r.description,
            ]
        )
        + " |"
        for r in rows
    ]
    return "\n".join([header, sep, *body, ""])


def check_manifest(root: Path, prev: Dict[str, Row]) -> int:
    ok_count = 0
    fail_count = 0
    for rel, row in sorted(prev.items()):
        target = root / rel
        if not target.exists() or not target.is_file():
            print(f"{rel}: FAILED (missing)")
            fail_count += 1
            continue

        current = crc32_checksum(target)
        if current == row.checksum_crc32:
            print(f"{rel}: OK")
            ok_count += 1
        else:
            print(f"{rel}: FAILED (expected {row.checksum_crc32}, got {current})")
            fail_count += 1
    print(f"checksum check: {ok_count} OK, {fail_count} FAILED")
    return 0 if fail_count == 0 else 1


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = root / manifest

    prev = parse_manifest(manifest)
    if args.check:
        return check_manifest(root, prev)

    files = collect_files(root, args.include, args.exclude, manifest)
    rows, mismatched_datetimes, synced_datetimes = build_rows(
        root,
        files,
        prev,
        sync_mtime_from_manifest=args.sync_mtime_from_manifest,
    )
    md = render_markdown(rows)

    if args.dry_run:
        print(md)
    else:
        manifest.write_text(md, encoding="utf-8")
        print(f"Updated {manifest} with {len(rows)} entries")

    if mismatched_datetimes:
        print("Files with same checksum but different modified_datetime from manifest:")
        for rel in mismatched_datetimes:
            print(f"- {rel}")
    if args.sync_mtime_from_manifest and synced_datetimes:
        print("Synced file mtime from manifest modified_datetime:")
        for rel in synced_datetimes:
            print(f"- {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
