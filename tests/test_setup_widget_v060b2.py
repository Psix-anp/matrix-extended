from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
INIT = COMP / "__init__.py"
CLIENT = COMP / "client.py"


def test_widget_runtime_is_wired_only_for_enabled_widget_panels() -> None:
    source = INIT.read_text(encoding="utf-8")
    assert "WidgetControlManager" in source
    assert "WidgetTransport" in source
    assert "widget_enabled" in source
    assert "WidgetControlManager(" in source
    assert "account.widget_manager = widget_manager" in source


def test_widget_callback_is_narrow_and_registered_independently() -> None:
    source = INIT.read_text(encoding="utf-8")
    assert "WIDGET_EVENT_TYPE" in source
    assert "add_to_device_callback" in source or ".add_callback(" in source
    assert "async_handle" in source
    assert "event.source" in source or "event.type" in source


def test_widget_manager_is_closed_on_unload() -> None:
    source = INIT.read_text(encoding="utf-8")
    assert "widget_manager" in source
    assert "await account.widget_manager.async_close()" in source


def test_matrix_account_exposes_widget_manager_runtime_slot() -> None:
    source = CLIENT.read_text(encoding="utf-8")
    assert "widget_manager: Any = None" in source
