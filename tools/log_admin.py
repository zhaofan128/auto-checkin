#!/usr/bin/env python3
"""Archive historical run.log files without touching the host run.log."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(data)
    temp.replace(path)


def _backup_dir(archive_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return archive_root / "_backup" / stamp


def archive(args: argparse.Namespace) -> int:
    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"source not found: {source}")
    data = source.read_bytes()
    digest = _sha256(data)
    lines = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)
    archive_root = Path(args.archive_root)
    target = archive_root / args.repo / "run.log"
    meta_path = archive_root / args.repo / "META.json"

    plan = {
        "source": str(source),
        "target": str(target),
        "sha256": digest,
        "bytes": len(data),
        "lines": lines,
        "source_commit": args.commit,
        "replace": args.replace,
    }
    if args.dry_run or not args.apply:
        print(json.dumps({"dry_run": True, **plan}, ensure_ascii=False, indent=2))
        return 0

    if target.exists() and not args.replace:
        raise SystemExit(f"target exists: {target}; use --replace to overwrite")

    backup_id = None
    if target.exists():
        backup = _backup_dir(archive_root)
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup / "run.log")
        if meta_path.exists():
            shutil.copy2(meta_path, backup / "META.json")
        backup_id = backup.name
        (backup / "backup.json").write_text(
            json.dumps({"target": str(target), "backup_id": backup_id}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    _write_atomic(target, data)
    meta = {
        "source_repo": args.source_repo,
        "source_commit": args.commit,
        "source_path": str(source),
        "archived_path": str(target),
        "sha256": digest,
        "bytes": len(data),
        "lines": lines,
        "archived_at": _now(),
        "backup_id": backup_id,
        "note": "historical only; not parsed into events.jsonl",
    }
    _write_atomic(meta_path, json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({"archived": True, **meta}, ensure_ascii=False, indent=2))
    return 0


def verify(args: argparse.Namespace) -> int:
    target = Path(args.archive_root) / args.repo / "run.log"
    meta_path = Path(args.archive_root) / args.repo / "META.json"
    if not target.is_file() or not meta_path.is_file():
        raise SystemExit("archive or META.json missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    actual = _sha256(target.read_bytes())
    ok = actual == meta.get("sha256")
    print(json.dumps({"ok": ok, "expected": meta.get("sha256"), "actual": actual}, indent=2))
    return 0 if ok else 1


def rollback(args: argparse.Namespace) -> int:
    archive_root = Path(args.archive_root)
    target = archive_root / args.repo / "run.log"
    meta_path = archive_root / args.repo / "META.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    backup_id = args.backup_id or meta.get("backup_id")
    if not backup_id:
        if target.exists():
            target.unlink()
        if meta_path.exists():
            meta_path.unlink()
        print(json.dumps({"rolled_back": True, "restored": False, "removed": str(target)}, indent=2))
        return 0
    backup = archive_root / "_backup" / backup_id
    backup_log = backup / "run.log"
    if not backup_log.is_file():
        raise SystemExit(f"backup not found: {backup_log}")
    _write_atomic(target, backup_log.read_bytes())
    print(json.dumps({"rolled_back": True, "restored": True, "backup_id": backup_id}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("archive")
    a.add_argument("--source", required=True)
    a.add_argument("--repo", required=True, help="archive subdirectory, e.g. kk-auto-checkin")
    a.add_argument("--source-repo", default="")
    a.add_argument("--commit", default="")
    a.add_argument("--archive-root", default="history/archive")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--apply", action="store_true")
    a.add_argument("--replace", action="store_true")
    a.set_defaults(func=archive)

    v = sub.add_parser("verify")
    v.add_argument("--repo", required=True)
    v.add_argument("--archive-root", default="history/archive")
    v.set_defaults(func=verify)

    r = sub.add_parser("rollback")
    r.add_argument("--repo", required=True)
    r.add_argument("--backup-id", default="")
    r.add_argument("--archive-root", default="history/archive")
    r.set_defaults(func=rollback)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
