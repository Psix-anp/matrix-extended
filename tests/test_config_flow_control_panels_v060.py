from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
CONFIG_FLOW = COMP / "config_flow.py"
STRINGS = COMP / "strings.json"
RU = COMP / "translations" / "ru.json"


def _class_method_source(class_name: str, method_name: str) -> str:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return ast.get_source_segment(source, child) or ""
    raise AssertionError(f"method not found: {class_name}.{method_name}")


def test_options_menu_exposes_control_panels() -> None:
    source = _class_method_source("MatrixExtendedOptionsFlow", "async_step_init")
    assert '"control_panels"' in source


def test_control_panel_menu_exposes_crud_repair_import_export() -> None:
    source = _class_method_source("MatrixExtendedOptionsFlow", "async_step_control_panels")
    for marker in (
        '"panel_add"',
        '"panel_edit"',
        '"panel_delete"',
        '"panel_repair"',
        '"panel_import"',
        '"panel_export_select"',
    ):
        assert marker in source


def test_panel_form_uses_native_entity_and_bounded_debounce_selectors() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert "EntitySelectorConfig(multiple=True)" in source
    assert "min=0.25" in source
    assert "max=10.0" in source
    assert "CONF_PANEL_DEBOUNCE" in source
    assert "CONF_PANEL_ALLOWED_USERS" in source


def test_panel_actions_are_graphically_managed_and_support_confirmation() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    for method in (
        "async_step_panel_action_add",
        "async_step_panel_action_edit",
        "async_step_panel_action_delete",
    ):
        assert f"def {method}" in source
    assert "CONF_PANEL_ACTION_CONFIRMATION_REQUIRED" in source
    assert "CONF_PANEL_ACTION_SERVICE" in source
    assert "CONF_PANEL_ACTION_TARGET" in source
    assert "CONF_PANEL_ACTION_DATA" in source


def test_panel_action_service_selector_matches_ha_2026_api() -> None:
    """HA 2026.9 has no ServiceSelector; use a SelectSelector service picker."""
    schema = _class_method_source("MatrixExtendedOptionsFlow", "_action_schema")
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert "ServiceSelector" not in source
    assert "SelectSelectorConfig" in schema
    assert "custom_value=True" in schema
    assert "_panel_service_options" in schema


def test_panel_save_reuses_pure_normalizer_and_runtime_policy() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert "normalize_control_panels" in source
    assert "account.incoming_policy.allowed_rooms" in source
    assert "account.incoming_policy.allowed_users" in source
    assert "CONF_CONTROL_PANELS" in source


def test_panel_repair_uses_runtime_manager_not_config_mutation() -> None:
    source = _class_method_source("MatrixExtendedOptionsFlow", "async_step_panel_repair")
    assert "account.panel_manager.async_repair" in source
    assert "self._finish" not in source


def test_panel_yaml_import_export_use_safe_shared_helpers() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert "load_panel_yaml" in source
    assert "dump_panel_yaml" in source
    assert "panel_import_confirm" in source


def test_control_panel_strings_exist_in_en_and_ru() -> None:
    en = json.loads(STRINGS.read_text(encoding="utf-8"))
    ru = json.loads(RU.read_text(encoding="utf-8"))
    for doc in (en, ru):
        steps = doc["options"]["step"]
        for key in (
            "control_panels",
            "panel_add",
            "panel_edit",
            "panel_edit_details",
            "panel_action_add",
            "panel_action_edit",
            "panel_action_delete",
            "panel_delete",
            "panel_repair",
            "panel_import",
            "panel_export_select",
            "panel_export",
        ):
            assert key in steps


def test_panel_configuration_preserves_unrelated_options_through_finish() -> None:
    source = _class_method_source("MatrixExtendedOptionsFlow", "_finish")
    assert "options = dict(self._entry.options)" in source
    assert "options.update(updates)" in source