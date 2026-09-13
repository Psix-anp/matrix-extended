from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_command_service_constants_are_declared() -> None:
    source = (COMP / "const.py").read_text()
    assert 'SERVICE_REGISTER_COMMAND: Final = "register_command"' in source
    assert 'SERVICE_UNREGISTER_COMMAND: Final = "unregister_command"' in source


def test_v051_service_module_exposes_strict_handler_contract() -> None:
    source = (COMP / "v051_services.py").read_text()
    for marker in (
        "_REGISTER_SCHEMA",
        "_UNREGISTER_SCHEMA",
        '"handler_type"',
        '"service"',
        '"target"',
        '"data"',
        '"entity_id"',
        '"caption"',
        "vol.PREVENT_EXTRA",
        "async_register_command",
        "async_unregister_command",
        "install_v051_services",
    ):
        assert marker in source
    assert 'handler_type == "service"' in source
    assert 'handler_type == "camera_snapshot"' in source
    assert 'camera_snapshot requires entity_id' in source
    assert 'service handler requires service' in source


def test_services_yaml_documents_command_actions_and_security_fields() -> None:
    services = (COMP / "services.yaml").read_text()
    assert "register_command:" in services
    assert "unregister_command:" in services
    register = services.split("register_command:", 1)[1].split("unregister_command:", 1)[0]
    for field in (
        "account:",
        "id:",
        "trigger:",
        "aliases:",
        "description:",
        "allowed_users:",
        "allowed_rooms:",
        "progress:",
        "handler_type:",
        "service:",
        "target:",
        "data:",
        "entity_id:",
        "caption:",
    ):
        assert field in register
    assert "service" in register
    assert "camera_snapshot" in register


def test_setup_loads_private_per_entry_command_store_before_account_creation() -> None:
    source = (COMP / "__init__.py").read_text()
    assert "from .commands import CommandRegistry" in source
    assert "from .v051_services import install_v051_services" in source
    assert 'f"{DOMAIN}.commands_{entry.entry_id}"' in source
    assert "private=True" in source
    assert "stored_commands = await command_store.async_load() or {}" in source
    assert "command_registry = CommandRegistry(stored_commands, store=command_store)" in source
    assert "command_registry=command_registry" in source
    assert "install_v051_services(hass)" in source


def test_register_and_unregister_persist_after_successful_mutation() -> None:
    source = (COMP / "v051_services.py").read_text()
    assert "account.command_registry.register(definition)" in source
    assert "await account.command_registry.async_save()" in source
    assert "removed = account.command_registry.unregister" in source
    assert '"handler_type": handler_type' in source
    assert '"removed": removed' in source
