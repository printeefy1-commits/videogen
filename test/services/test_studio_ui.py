from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


def test_studio_pages_and_unconfigured_provider(monkeypatch):
    for name in ("FREELLM_API_KEY", "FREELLM_BASE_URL", "FREELLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    app = AppTest.from_file(str(ROOT / "webui/Studio.py"), default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "Big ideas. Short videos."
    app.button(key="write_script").click().run()
    assert not app.exception
    assert any("configure" in item.value for item in app.error)
    for page in ("Edit video", "My library", "API settings"):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception


def test_environment_key_is_not_sent_to_the_settings_widget(monkeypatch):
    monkeypatch.setenv("FREELLM_API_KEY", "test-secret-never-rendered")
    app = AppTest.from_file(str(ROOT / "webui/Studio.py"), default_timeout=60).run()
    app.sidebar.radio[0].set_value("API settings").run()
    assert not app.exception
    key_widget = next(widget for widget in app.text_input if widget.label == "API key")
    assert key_widget.disabled
    assert key_widget.value == ""
