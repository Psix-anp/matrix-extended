"""Generate non-secret Matrix Widget configuration for Native Matrix Control."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote


def build_widget_config(
    *,
    base_url: str,
    panel_id: str,
    title: str,
    user_id: str,
    device_id: str,
) -> dict[str, Any]:
    """Return a Matrix Widget state payload without credentials or HA secrets."""
    base = str(base_url).strip().rstrip("#")
    if not base:
        raise ValueError("widget base URL is required")
    panel = str(panel_id).strip()
    if not panel:
        raise ValueError("panel_id is required")
    matrix_user = str(user_id).strip()
    matrix_device = str(device_id).strip()
    if not matrix_user or not matrix_device:
        raise ValueError("Matrix user_id and device_id are required")

    fragment = (
        "room_id=$matrix_room_id"
        "&matrix_user_id=$matrix_user_id"
        "&widget_id=$matrix_widget_id"
        f"&panel_id={quote(panel, safe='')}"
        f"&integration_user_id={quote(matrix_user, safe='')}"
        f"&integration_device_id={quote(matrix_device, safe='')}"
    )
    return {
        "id": f"matrix_extended_{panel}",
        "type": "m.custom",
        "name": str(title or panel),
        "url": f"{base}#{fragment}",
        "data": {
            "panel_id": panel,
            "integration_user_id": matrix_user,
            "integration_device_id": matrix_device,
            "protocol": "io.psix.matrix_extended.widget.v1",
        },
    }
