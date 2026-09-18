"""Shared bounded action definitions for Matrix Extended control surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class ServiceActionHandler:
    """Preconfigured Home Assistant service action."""

    service: str
    target: dict[str, Any]
    data: dict[str, Any]


@dataclass(slots=True, frozen=True)
class CameraSnapshotActionHandler:
    """Preconfigured camera snapshot action."""

    entity_id: str
    caption: str


@dataclass(slots=True, frozen=True)
class SafeActionDefinition:
    """Stable action definition referenced by Matrix control inputs."""

    id: str
    handler: ServiceActionHandler | CameraSnapshotActionHandler
    confirmation_required: bool = False


def _mapping(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return dict(value)


def parse_service_handler(value: Mapping[str, Any]) -> ServiceActionHandler:
    """Validate and copy a Home Assistant service handler definition."""
    if not isinstance(value, Mapping):
        raise ValueError("service handler must be an object")
    service = str(value.get("service", "")).strip()
    if service.count(".") != 1 or any(not part for part in service.split(".", 1)):
        raise ValueError("service must use domain.service format")
    return ServiceActionHandler(
        service=service,
        target=_mapping(value.get("target"), name="target"),
        data=_mapping(value.get("data"), name="data"),
    )


def parse_camera_snapshot_handler(
    value: Mapping[str, Any],
) -> CameraSnapshotActionHandler:
    """Validate and copy a bounded camera snapshot handler definition."""
    if not isinstance(value, Mapping):
        raise ValueError("camera snapshot handler must be an object")
    entity_id = str(value.get("entity_id", "")).strip()
    if not entity_id.startswith("camera.") or len(entity_id) <= len("camera."):
        raise ValueError("camera_snapshot entity_id must be a camera.* entity")
    caption = str(value.get("caption", "Camera snapshot")).strip() or "Camera snapshot"
    return CameraSnapshotActionHandler(entity_id=entity_id, caption=caption)


def dump_action_handler(
    handler: ServiceActionHandler | CameraSnapshotActionHandler,
) -> dict[str, Any]:
    """Return a stable JSON-safe handler mapping."""
    if isinstance(handler, ServiceActionHandler):
        return {
            "type": "service",
            "service": handler.service,
            "target": dict(handler.target),
            "data": dict(handler.data),
        }
    if isinstance(handler, CameraSnapshotActionHandler):
        return {
            "type": "camera_snapshot",
            "entity_id": handler.entity_id,
            "caption": handler.caption,
        }
    raise ValueError("unsupported safe action handler")


def dump_safe_action(action: SafeActionDefinition) -> dict[str, Any]:
    """Return a stable JSON-safe action mapping."""
    return {
        "id": action.id,
        "confirmation_required": bool(action.confirmation_required),
        "handler": dump_action_handler(action.handler),
    }
