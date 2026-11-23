from pathlib import Path

from tools.log_admin import main


def test_archive_dry_run_apply_verify_and_rollback(tmp_path: Path):
    source = tmp_path / "kk-run.log"
    source.write_text("2026-11-22 10:30:10 CST check-in run\n", encoding="utf-8")
    host_log = tmp_path / "host-history" / "run.log"
    host_log.parent.mkdir()
    host_log.write_text("host original\n", encoding="utf-8")
    archive_root = tmp_path / "archive"

    assert main(
        [
            "archive",
            "--source",
            str(source),
            "--repo",
            "kk-auto-checkin",
            "--source-repo",
            "zhaofan128/kk-auto-checkin",
            "--commit",
            "abc123",
            "--archive-root",
            str(archive_root),
            "--dry-run",
        ]
    ) == 0
    target = archive_root / "kk-auto-checkin" / "run.log"
    assert not target.exists()

    assert main(
        [
            "archive",
            "--source",
            str(source),
            "--repo",
            "kk-auto-checkin",
            "--source-repo",
            "zhaofan128/kk-auto-checkin",
            "--commit",
            "abc123",
            "--archive-root",
            str(archive_root),
            "--apply",
        ]
    ) == 0
    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert (archive_root / "kk-auto-checkin" / "META.json").is_file()
    assert host_log.read_text(encoding="utf-8") == "host original\n"

    assert main(["verify", "--repo", "kk-auto-checkin", "--archive-root", str(archive_root)]) == 0

    target.write_text("tampered\n", encoding="utf-8")
    assert main(["verify", "--repo", "kk-auto-checkin", "--archive-root", str(archive_root)]) == 1

    assert main(["rollback", "--repo", "kk-auto-checkin", "--archive-root", str(archive_root)]) == 0
    assert not target.exists()
