#!/usr/bin/env python3
"""Single unified entry point for the check-in runner."""

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=None,
        help="quota/qoder/morning/midmorning/afternoon/manual",
    )
    parser.add_argument(
        "--platform",
        action="append",
        default=[],
        help="Limit to one or more platform keys; repeatable",
    )
    parser.add_argument("--dry-run", action="store_true", help="Read status/points only")
    parser.add_argument("--force", action="store_true", help="Bypass already-checked guards")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base = Settings.from_env()
    profile = args.profile or base.default_profile
    settings = Settings(
        repo=base.repo,
        gh_token=base.gh_token,
        history_dir=base.history_dir,
        state_dir=base.state_dir,
        timezone=base.timezone,
        default_profile=profile,
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
    runner = Runner(
        registry=registry,
        secrets=secrets,
        state=state,
        logger=logger,
        refresher=RefreshCoordinator(state, secrets, github),
        http=HttpClient(timeout_s=settings.timeout_s),
        settings=settings,
    )

    platforms = set(args.platform) or None
    report = runner.run(
        profile=profile,
        platforms=platforms,
        dry_run=args.dry_run,
        force=args.force,
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
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
