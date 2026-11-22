from pathlib import Path

import pytest

from src.core.errors import StateConflict
from src.core.models import AccountRef
from src.core.state import AccountStateStore, default_state


def account(platform: str, account_id: str, key: str) -> AccountRef:
    return AccountRef(
        platform=platform,
        platform_name=platform,
        account_id=account_id,
        account_key=key,
        account_label=account_id,
    )


def test_state_round_trip_and_cas(tmp_path: Path):
    store = AccountStateStore(tmp_path)
    ref = account("workbuddy", "default", "workbuddy:default")
    initial = store.load(ref)
    assert initial.generation == 0

    store.save(initial)
    loaded = store.load(ref)
    assert loaded.account_key == "workbuddy:default"

    with pytest.raises(StateConflict):
        store.save(initial, expected_generation=1)

    bumped = store.bump_generation(ref, expected_generation=0)
    assert bumped.generation == 1
    assert store.load(ref).generation == 1


def test_qoder_state_files_are_separate(tmp_path: Path):
    store = AccountStateStore(tmp_path)
    cn = account("qoder_cn", "cn", "qoder:cn")
    global_account = account("qoder_global", "global", "qoder:global")

    assert store.path_for(cn) == tmp_path / "qoder" / "qoder_cn.json"
    assert store.path_for(global_account) == tmp_path / "qoder" / "qoder_global.json"
    assert store.path_for(cn) != store.path_for(global_account)

    store.save(default_state(cn))
    store.save(default_state(global_account))
    assert store.path_for(cn).exists()
    assert store.path_for(global_account).exists()


def test_qoder_locks_are_separate(tmp_path: Path):
    store = AccountStateStore(tmp_path)
    cn = account("qoder_cn", "cn", "qoder:cn")
    global_account = account("qoder_global", "global", "qoder:global")

    with store.lock(cn, timeout_s=0.2):
        with store.lock(global_account, timeout_s=0.2):
            pass
