import os

from screentutor import settings
from screentutor.settings import Settings, Watch


def test_missing_or_broken_file_gives_the_defaults(tmp_path, capsys):
    assert settings.load(tmp_path / "none.json") == Settings()
    bad = tmp_path / "settings.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert settings.load(bad) == Settings()
    assert "mặc định" in capsys.readouterr().out
    bad.write_text("[1, 2]", encoding="utf-8")
    assert settings.load(bad) == Settings()


def test_a_wrong_type_keeps_the_default_for_that_key_only(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text('{"show_button": "no", "island_color": "#102030", "extra": 1}', encoding="utf-8")
    s = settings.load(f)
    assert s.show_button is True and s.island_color == "#102030"


def test_save_and_load_round_trip(tmp_path):
    f = tmp_path / "settings.json"
    settings.save(Settings(show_button=False, island_color="#000000"), f)
    assert settings.load(f) == Settings(show_button=False)
    assert '"show_button": false' in f.read_text(encoding="utf-8")


def test_watch_sees_a_change_appear_and_go(tmp_path):
    f = tmp_path / "settings.json"
    w = Watch(f)
    assert w.poll() is None
    settings.save(Settings(show_button=False), f)
    assert w.poll() == Settings(show_button=False)
    assert w.poll() is None  # nothing new since
    settings.save(Settings(show_button=True), f)
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert w.poll() == Settings(show_button=True)
    f.unlink()
    assert w.poll() == Settings()


def test_settings_file_lives_next_to_the_app_and_is_not_committed():
    assert settings.PATH.parent == settings.ROOT and settings.PATH.name == "settings.json"
    ignored = (settings.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "settings.json" in ignored and "history/" in ignored
