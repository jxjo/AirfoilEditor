import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from airfoileditor.base import app_utils
from airfoileditor.base.app_utils import Recent_Files, Settings, Update_Checker


@pytest.fixture
def history_settings(tmp_path, monkeypatch):
    filename = tmp_path / "settings.json"
    monkeypatch.setattr(Settings, "_pathFileName", str(filename))
    return filename


def test_legacy_migration_and_clear_do_not_change_resume_file(history_settings, tmp_path):
    airfoil = tmp_path / "old.dat"
    airfoil.touch()
    history_settings.write_text(json.dumps({"last_opened": str(airfoil), "other": 12}))
    history = Recent_Files()
    assert history.paths == [airfoil]
    saved = json.loads(history_settings.read_text())
    assert saved["recent_files"] == [str(airfoil)]
    assert saved["last_opened"] == str(airfoil)
    history.clear()
    assert Recent_Files().paths == []
    saved = json.loads(history_settings.read_text())
    assert saved["last_opened"] == str(airfoil)
    assert saved["other"] == 12


def test_add_deduplicates_normalizes_and_limits(history_settings, tmp_path):
    files = [tmp_path / f"foil{i}.dat" for i in range(12)]
    for path in files:
        path.touch()
        Recent_Files().add(path)
    history = Recent_Files()
    assert history.paths == list(reversed(files))[:10]
    history.add(str(tmp_path / ".." / tmp_path.name / files[4].name))
    assert history.paths[0] == files[4]
    assert len(history.paths) == 10
    assert history.paths.count(files[4]) == 1
    if Path("A") == Path("a"):
        history.add(str(files[4]).upper())
        assert len(history.paths) == 10
        assert history.paths.count(files[4]) == 1


def test_separate_instances_keep_history_and_unrelated_settings(history_settings, tmp_path):
    a, b = tmp_path / "a.dat", tmp_path / "b.dat"
    a.touch()
    b.touch()
    first, second = Recent_Files(), Recent_Files()
    first.add(a)
    settings = Settings()
    settings.set("unrelated", True)
    settings.save()
    second.add(b)
    assert first.paths == [b, a]
    assert Settings().get("unrelated") is True
    first.remove(a)
    assert second.paths == [b]


def test_independent_history_keys(history_settings, tmp_path):
    path = tmp_path / "project.pc2"
    path.touch()
    Recent_Files(key="recent_projects", legacy_key=None).add(path)
    assert Recent_Files().paths == []
    assert Recent_Files(key="recent_projects", legacy_key=None).paths == [path]


def test_missing_files_are_not_added_or_implicitly_removed(history_settings, tmp_path, caplog):
    missing = tmp_path / "missing.dat"
    history = Recent_Files()
    history.add(missing)
    assert "Not adding missing file" in caplog.text
    missing.touch()
    history.add(missing)
    missing.unlink()
    assert history.paths == [missing]
    history.remove(missing)
    assert history.paths == []


def test_missing_legacy_file_is_not_migrated(history_settings, tmp_path):
    history_settings.write_text(json.dumps({"last_opened": str(tmp_path / "missing.dat")}))
    assert Recent_Files().paths == []


def test_delayed_update_preference_does_not_overwrite_new_history(history_settings, tmp_path, monkeypatch):
    checker = SimpleNamespace(_settings=Settings(), _latest_version="99.0",
                              _app_name="test", _package_name="test")
    path = tmp_path / "foil.dat"
    path.touch()
    Recent_Files().add(path)
    monkeypatch.setattr(app_utils, "Update_Info_Dialog",
                        Mock(return_value=Mock(dont_ask_version=True)))
    Update_Checker.show_user_info(checker, None)
    assert Recent_Files().paths == [path]
    assert Settings().get("update_dont_ask_for_version") == "99.0"
