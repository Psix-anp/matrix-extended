from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
TESTS = ROOT / "tests"
COMP = ROOT / "custom_components" / "matrix_extended"


def load_helper(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, TESTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_manager_diagnostics_snapshot_is_bounded_and_secret_free() -> None:
    helper = load_helper("test_control_panel_manager_v060.py", "panel_diag_helper_v060")
    modules = helper.load_modules()
    manager, store, _, _, _ = helper.build_manager(modules)
    runtime_mod = modules["control_panel_runtime"]
    store.set(
        runtime_mod.PanelRuntime(
            panel_id="garage",
            room_id="!garage:example",
            root_event_id="$root",
            generation=2,
            pin_status="pinned",
            last_update_at=123.0,
            last_update_error=None,
        )
    )

    snapshots = manager.diagnostics_snapshot()

    assert len(snapshots) == 1
    item = snapshots[0]
    assert set(item) == {
        "panel_id",
        "room_id",
        "root_event_id",
        "state",
        "pin_status",
        "watched_entities",
        "actions",
        "last_update_at",
        "last_update_error",
        "pending_confirmations",
    }
    assert item["panel_id"] == "garage"
    assert item["state"] == "active"
    rendered = json.dumps(item).lower()
    for forbidden in ("service", "target", "data", "token", "password", "secret"):
        assert forbidden not in rendered


def test_manager_listener_contract_covers_diagnostics_changes() -> None:
    source = (COMP / "control_panel_manager.py").read_text(encoding="utf-8")
    assert "def add_listener" in source
    assert "self._notify()" in source
    assert "self.confirmations.issue(" in source
    assert "self.confirmations.consume(" in source
    assert "self.confirmations.cancel(" in source


def test_sensor_platform_adds_disabled_control_panel_diagnostics_sensor() -> None:
    source = (COMP / "sensor.py").read_text(encoding="utf-8")
    for marker in (
        "MatrixControlPanelsSensor",
        '_attr_translation_key = "control_panels"',
        "_attr_entity_registry_enabled_default = False",
        "panel_manager.add_listener(self.async_write_ha_state)",
        "panel_manager.diagnostics_snapshot()",
    ):
        assert marker in source


def test_control_panel_sensor_value_counts_active_panels_only() -> None:
    source = (COMP / "sensor.py").read_text(encoding="utf-8")
    assert 'item.get("state") == "active"' in source
    assert 'return sum(' in source


def test_control_panel_sensor_attributes_are_bounded_snapshot_only() -> None:
    source = (COMP / "sensor.py").read_text(encoding="utf-8")
    assert 'return {"panels": snapshots}' in source
    assert "service_data" not in source
    assert "access_token" not in source


def test_control_panel_diagnostic_translation_key_exists_in_en_and_ru() -> None:
    en = json.loads((COMP / "strings.json").read_text(encoding="utf-8"))
    ru = json.loads((COMP / "translations" / "ru.json").read_text(encoding="utf-8"))
    for doc in (en, ru):
        assert "control_panels" in doc["entity"]["sensor"]
