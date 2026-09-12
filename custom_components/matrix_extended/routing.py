"""Routing helpers for Matrix Extended."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        target = str(value).strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result


def normalize_routing_profiles(value: object) -> dict[str, list[str]]:
    """Normalize user-provided route mapping into route -> room targets."""
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("routing_profiles must be a mapping of route names to room lists")
    result: dict[str, list[str]] = {}
    for raw_name, raw_targets in value.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("routing profile names cannot be blank")
        if isinstance(raw_targets, str):
            targets = [raw_targets]
        elif isinstance(raw_targets, Mapping):
            raise ValueError(f"Matrix route '{name}' must contain a room list")
        elif isinstance(raw_targets, Iterable):
            targets = list(raw_targets)
        else:
            raise ValueError(f"Matrix route '{name}' must contain a room list")
        result[name] = _dedupe(str(item) for item in targets)
    return result


def resolve_targets(
    *,
    explicit_targets: list[str] | None,
    route: str | None,
    default_room: str,
    routing_profiles: Mapping[str, list[str]],
) -> list[str]:
    """Resolve an outbound target list using explicit targets, route, or default."""
    if explicit_targets and route:
        raise ValueError("target and route are mutually exclusive")
    if explicit_targets:
        targets = _dedupe(explicit_targets)
        if not targets:
            raise ValueError("target has no rooms")
        return targets
    if route:
        if route not in routing_profiles:
            raise ValueError(f"Unknown Matrix route: {route}")
        targets = _dedupe(routing_profiles[route])
        if not targets:
            raise ValueError(f"Matrix route '{route}' has no rooms")
        return targets
    default = str(default_room).strip()
    if not default:
        raise ValueError("Matrix default room is empty")
    return [default]
