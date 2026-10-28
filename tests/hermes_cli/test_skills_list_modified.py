"""Installed-skill modification indicators compare real files against current stock."""

import shutil
from io import StringIO

import pytest
from rich.console import Console

from hermes_cli import skills_hub as cli_hub
from tools.skills_sync_bundled_ops import diff_bundled_skill


@pytest.fixture()
def installed_tree(tmp_path, monkeypatch):
    from agent.skill_utils import TIER_LOCAL
    from tools import skills_hub as hub, skills_sync, skills_tool

    bundled = tmp_path / "bundled"
    stock = bundled / "category" / "foo"
    stock.mkdir(parents=True)
    (stock / "SKILL.md").write_text("---\nname: foo\ndescription: Foo skill\n---\n# Foo\n", encoding="utf-8")
    (stock / "references").mkdir()
    (stock / "references" / "guide.md").write_text("Stock guide\n", encoding="utf-8")
    skills = tmp_path / "skills"
    local = skills / "category" / "foo"
    shutil.copytree(stock, local)
    monkeypatch.setattr(skills_sync, "_get_bundled_dir", lambda: bundled)
    monkeypatch.setattr(skills_sync, "SKILLS_DIR", skills)
    monkeypatch.setattr(skills_sync, "MANIFEST_FILE", skills / ".bundled_manifest")
    skills_sync._write_manifest({"foo": skills_sync.dir_hash(stock)})
    monkeypatch.setattr(skills_tool, "skill_search_dirs", lambda: ([(TIER_LOCAL, skills)], skills))
    for attr, path in {
        "SKILLS_DIR": skills, "HUB_DIR": skills / ".hub",
        "LOCK_FILE": skills / ".hub" / "lock.json",
        "QUARANTINE_DIR": skills / ".hub" / "quarantine",
        "AUDIT_LOG": skills / ".hub" / "audit.log",
        "TAPS_FILE": skills / ".hub" / "taps.json",
        "INDEX_CACHE_DIR": skills / ".hub" / "index-cache",
    }.items():
        monkeypatch.setattr(hub, attr, path)
    return stock, local


def _list_text(**kwargs):
    sink = StringIO()
    console = Console(file=sink, force_terminal=False, color_system=None, width=160)
    cli_hub.do_list(console=console, **kwargs)
    return sink.getvalue()


@pytest.mark.parametrize("changes, stale_manifest, expected", [
    pytest.param([], False, False, id="pristine"),
    pytest.param([("local", "SKILL.md", b"---\nname: foo\n---\nMy instructions\n")], False, True, id="skill"),
    pytest.param([("local", "references/guide.md", b"My guide\n")], False, True, id="reference"),
    pytest.param([("local", "notes.md", b"My notes\n")], False, True, id="added"),
    pytest.param([("local", "references/guide.md", None)], False, True, id="removed"),
    pytest.param([("stock", "image.bin", b"stock\x00"), ("local", "image.bin", b"mine\x00")], False, True, id="binary"),
    pytest.param([("local", "__pycache__/helper.pyc", b"runtime cache")], False, False, id="cache"),
    pytest.param([("stock", "references/guide.md", b"New upstream guide\n")], False, True, id="upstream"),
    pytest.param([], True, False, id="stale_manifest"),
])
def test_list_modified_agrees_with_diff_for_real_files(installed_tree, changes, stale_manifest, expected):
    from tools import skills_sync

    stock, local = installed_tree
    roots = {"stock": stock, "local": local}
    for root, relative, content in changes:
        path = roots[root] / relative
        if content is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if stale_manifest:
        skills_sync._write_manifest({"foo": "old-origin-hash"})

    assert diff_bundled_skill("foo")["modified"] is expected
    output = _list_text()
    assert "Modified" not in output
    row = next(line for line in output.splitlines() if "foo" in line)
    assert ("builtin*" in row) is expected
    assert "foo*" not in row
    assert ("* modified from stock" in output) is expected
    assert "builtin" in row
    assert "enabled" in row
    assert "1 builtin" in output


def test_list_keeps_missing_stock_as_builtin_without_claiming_unmodified(installed_tree):
    stock, local = installed_tree
    shutil.rmtree(stock)

    output = _list_text()

    row = next(line for line in output.splitlines() if "foo" in line)
    assert "builtin" in row
    assert "builtin*" not in row
    assert "* modified from stock" not in output
    assert local.is_dir()


def test_list_preserves_hub_local_and_enabled_filters(installed_tree, monkeypatch):
    from agent import skill_utils
    from tools import skills_hub as hub

    _, local = installed_tree
    other = local.parent / "bar"
    other.mkdir()
    (other / "SKILL.md").write_text("---\nname: bar\ndescription: Local\n---\n", encoding="utf-8")
    (local / "references" / "guide.md").write_text("Edited\n", encoding="utf-8")
    monkeypatch.setattr(hub, "HubLockFile", lambda: type("Lock", (), {
        "list_installed": lambda self: [{"name": "foo", "source": "github", "trust_level": "community"}],
    })())
    monkeypatch.setattr(skill_utils, "get_disabled_skill_names", lambda: {"foo"})

    output = _list_text()
    hub_row = next(line for line in output.splitlines() if "foo" in line)
    local_row = next(line for line in output.splitlines() if "bar" in line)
    assert all(value in hub_row for value in ("github", "community", "disabled"))
    assert all(value in local_row for value in ("local", "enabled"))
    assert "*" not in hub_row + local_row
    assert "1 hub-installed, 0 builtin, 1 local" in output
    assert "1 enabled, 1 disabled" in output
    assert "foo" not in _list_text(enabled_only=True)
    assert "bar" not in _list_text(source_filter="hub")
    assert "foo" not in _list_text(source_filter="local")
    assert "foo" not in _list_text(source_filter="builtin")


def test_disabled_builtin_retains_modified_indicator(installed_tree, monkeypatch):
    from agent import skill_utils

    _, local = installed_tree
    (local / "references" / "guide.md").unlink()
    monkeypatch.setattr(skill_utils, "get_disabled_skill_names", lambda: {"foo"})

    output = _list_text(source_filter="builtin")

    row = next(line for line in output.splitlines() if "foo" in line)
    assert all(value in row for value in ("foo", "builtin*", "disabled"))
    assert "foo" not in _list_text(enabled_only=True)


def test_missing_local_copy_is_not_added_to_list(installed_tree):
    _, local = installed_tree
    shutil.rmtree(local)

    output = _list_text()

    assert "foo" not in output
    assert "0 builtin" in output
