"""The bridge spawn retries without job breakaway when a parent job denies it."""

import pytest

from hermes_cli._subprocess_compat import windows_detach_flags, windows_detach_flags_without_breakaway
from plugins.platforms.whatsapp import adapter


def _denied() -> OSError:
    exc = PermissionError(13, "Access is denied")
    exc.winerror = 5
    return exc


def test_retries_without_breakaway_when_job_denies_it(monkeypatch):
    seen = []

    def fake_spawn_owned(argv, *, purpose, **kwargs):
        seen.append(kwargs["creationflags"])
        if kwargs["creationflags"] == windows_detach_flags():
            raise _denied()
        return "proc"

    monkeypatch.setattr(adapter, "spawn_owned", fake_spawn_owned)
    monkeypatch.setattr(adapter, "windows_detach_flags", windows_detach_flags)

    assert adapter._spawn_bridge_process(["node"], None, {}) == "proc"
    expected = [windows_detach_flags(), windows_detach_flags_without_breakaway()]
    assert seen == (expected if windows_detach_flags() != windows_detach_flags_without_breakaway() else [0, 0])


def test_other_spawn_errors_are_not_retried(monkeypatch):
    calls = []

    def fake_spawn_owned(argv, *, purpose, **kwargs):
        calls.append(1)
        raise FileNotFoundError(2, "missing")

    monkeypatch.setattr(adapter, "spawn_owned", fake_spawn_owned)
    with pytest.raises(FileNotFoundError):
        adapter._spawn_bridge_process(["node"], None, {})
    assert calls == [1]
