from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


init_path = Path("custom_components/matrix_extended/__init__.py")
text = init_path.read_text()
text = replace_once(
    text,
    "from .actions import ReactionActionRegistry\n",
    "from .actions import ReactionActionRegistry\nfrom .commands import CommandRegistry\n",
    label="CommandRegistry import",
)
text = replace_once(
    text,
    "from .v05_services import install_v05_services\n",
    "from .v05_services import install_v05_services\nfrom .v051_services import install_v051_services\n",
    label="v051 services import",
)
text = replace_once(
    text,
    "    install_v05_services(hass)\n    return True\n",
    "    install_v05_services(hass)\n    install_v051_services(hass)\n    return True\n",
    label="v051 service install",
)
text = replace_once(
    text,
    "    stored_actions = await action_store.async_load() or {}\n"
    "    action_registry = ReactionActionRegistry(stored_actions, store=action_store)\n"
    "    outbox_store: Store[dict[str, Any]] = Store(\n",
    "    stored_actions = await action_store.async_load() or {}\n"
    "    action_registry = ReactionActionRegistry(stored_actions, store=action_store)\n"
    "    command_store: Store[dict[str, Any]] = Store(\n"
    "        hass, 1, f\"{DOMAIN}.commands_{entry.entry_id}\", private=True\n"
    "    )\n"
    "    stored_commands = await command_store.async_load() or {}\n"
    "    command_registry = CommandRegistry(stored_commands, store=command_store)\n"
    "    outbox_store: Store[dict[str, Any]] = Store(\n",
    label="command store",
)
text = replace_once(
    text,
    "        action_registry=action_registry,\n        outbox=outbox,\n",
    "        action_registry=action_registry,\n        command_registry=command_registry,\n        outbox=outbox,\n",
    label="account registry",
)
init_path.write_text(text)

services_path = Path("custom_components/matrix_extended/services.yaml")
services = services_path.read_text()
if "register_command:" in services or "unregister_command:" in services:
    raise SystemExit("command services already present; refusing duplicate append")
services += """

register_command:
  name: Register safe Matrix command
  description: Register or replace one exact Matrix command. Incoming Matrix text can select only this stored command and cannot override its Home Assistant service, target, data, or camera entity.
  fields:
    account: {name: Account, selector: {text: {}}}
    id: {name: Command ID, required: true, selector: {text: {}}}
    trigger:
      name: Trigger
      description: Exact normalized phrase without the leading exclamation mark, for example garage open.
      required: true
      selector: {text: {}}
    aliases:
      name: Aliases
      selector: {text: {multiple: true}}
    description: {name: Description, selector: {text: {}}}
    allowed_users:
      name: Allowed users
      description: Optional users that further narrow the account allowlist.
      selector: {text: {multiple: true}}
    allowed_rooms:
      name: Allowed rooms
      description: Optional rooms that further narrow the account allowlist.
      selector: {text: {multiple: true}}
    progress: {name: Progress reply, default: true, selector: {boolean: {}}}
    handler_type:
      name: Handler type
      required: true
      selector: {select: {options: [service, camera_snapshot]}}
    service:
      name: Home Assistant service
      description: Required only for service handlers.
      selector: {text: {}}
    target:
      name: Stored service target
      description: Never derived from incoming Matrix text.
      selector: {object: {}}
    data:
      name: Stored service data
      description: Never derived from incoming Matrix text.
      selector: {object: {}}
    entity_id:
      name: Camera entity
      description: Required only for camera_snapshot and must be camera.*.
      selector: {entity: {domain: camera}}
    caption: {name: Camera caption, selector: {text: {}}}

unregister_command:
  name: Unregister safe Matrix command
  description: Remove one registered Matrix command by stable ID.
  fields:
    account: {name: Account, selector: {text: {}}}
    id: {name: Command ID, required: true, selector: {text: {}}}
"""
services_path.write_text(services)
