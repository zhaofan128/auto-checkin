from pathlib import Path

from src.config.registry import build_default_registry


def test_default_registry_has_13_accounts():
    registry = build_default_registry()
    specs = registry.all_specs()
    assert len(specs) == 13
    keys = [spec.account_key for spec in specs]
    assert keys == [
        "workbuddy:default",
        "traework:cn",
        "qoder:cn",
        "qoder:global",
        "minimax:default",
        "lobsterai:default",
        "kk:default",
        "dgb:default",
        "aiaiai:default",
        "helpcoder:default",
        "kemeng:default",
        "seekai:default",
        "benst:default",
    ]


def test_qoder_accounts_are_separate_in_registry():
    registry = build_default_registry()
    cn = registry.get_spec("qoder:cn")
    global_account = registry.get_spec("qoder:global")
    assert cn.platform == "qoder_cn"
    assert global_account.platform == "qoder_global"
    assert cn.rolling is True
    assert global_account.rolling is False


def test_schedule_profiles_select_expected_accounts():
    registry = build_default_registry()
    assert {spec.account_key for spec in registry.select("quota")} == {"benst:default"}
    assert {spec.account_key for spec in registry.select("qoder")} == {"qoder:cn", "qoder:global"}
    assert len(registry.select("morning")) == 13
