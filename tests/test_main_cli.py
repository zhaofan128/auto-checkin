from pathlib import Path

from src.main import main


def test_main_entry_degrades_without_secrets(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("CHECKIN_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("CHECKIN_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CHECKIN_GITHUB_REPO", "")
    monkeypatch.setenv("GITHUB_REPOSITORY", "")
    monkeypatch.setenv("GH_PAT", "")
    monkeypatch.setenv("GH_TOKEN", "")
    monkeypatch.setenv("GITHUB_TOKEN", "")

    code = main(["--platform", "workbuddy", "--dry-run"])
    out = capsys.readouterr().out

    assert code == 0
    assert '"skipped": 1' in out
    assert (tmp_path / "history" / "events.jsonl").is_file()
    assert list((tmp_path / "state").rglob("*.json"))
