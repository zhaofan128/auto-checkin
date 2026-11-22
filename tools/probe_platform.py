#!/usr/bin/env python3
"""Probe one platform through the unified core and print redacted events.

Default is dry-run: status/points only, no claim. Dry-run still refreshes
rolling tokens and writes them back when GH_PAT is available, because the
refresh token is single-use.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.registry import build_default_registry
from src.config.settings import Settings
from src.core.github import GhCliGitHubSecrets, NullGitHubSecrets
from src.core.http import HttpClient
from src.core.logging import EventLogger, new_run_id
from src.core.refresh import RefreshCoordinator
from src.core.runner import Runner
from src.core.secrets import SecretResolver
from src.core.state import AccountStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform",
        default="workbuddy",
        choices=[
            "workbuddy",
            "traework",
            "qoder_cn",
            "qoder_global",
            "minimax",
            "lobsterai",
            "kk",
            "dgb",
            "aiaiai",
            "helpcoder",
            "kemeng",
            "seekai",
            "benst",
        ],
    )
    parser.add_argument("--apply", action="store_true", help="真正签到；默认 dry-run")
    parser.add_argument("--history-dir", default=".probe/history")
    parser.add_argument("--state-dir", default=".probe/state")
    parser.add_argument("--json", action="store_true", help="输出脱敏后的 JSONL 事件")
    args = parser.parse_args()

    base = Settings.from_env()
    settings = Settings(
        repo=base.repo,
        gh_token=base.gh_token,
        history_dir=Path(args.history_dir),
        state_dir=Path(args.state_dir),
        timezone=base.timezone,
        default_profile="manual",
        timeout_s=base.timeout_s,
    )
    settings.ensure_dirs()

    github = (
        GhCliGitHubSecrets(settings.repo, token=settings.gh_token)
        if settings.repo
        else NullGitHubSecrets()
    )
    secrets = SecretResolver(dict(os.environ), github=github)
    state = AccountStateStore(settings.state_dir)
    run_id = new_run_id()
    logger = EventLogger(settings.history_dir, run_id=run_id)
    registry = build_default_registry()
    if not any(spec.platform == args.platform for spec in registry.all_specs()):
        raise SystemExit(f"未知平台: {args.platform}")
    runner = Runner(
        registry=registry,
        secrets=secrets,
        state=state,
        logger=logger,
        refresher=RefreshCoordinator(state, secrets, github),
        http=HttpClient(),
        settings=settings,
    )

    report = runner.run(
        profile="manual",
        platforms={args.platform},
        dry_run=not args.apply,
        force=True,
    )
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "profile": report.profile,
                "counts": report.counts,
                "skipped_reasons": report.skipped_reasons,
                "exit_code": report.exit_code,
            },
            ensure_ascii=False,
        )
    )
    current = [event for event in logger.read_events() if event.get("run_id") == report.run_id]
    for event in current:
        print(json.dumps(event, ensure_ascii=False, indent=2 if args.json else None))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
