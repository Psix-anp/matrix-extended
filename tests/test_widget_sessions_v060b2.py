from __future__ import annotations

from custom_components.matrix_extended.widget_sessions import WidgetSessionRegistry


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_subscribe_is_immediate_and_heartbeat_refreshes_90_second_ttl():
    clock = Clock()
    registry = WidgetSessionRegistry(now=clock)
    sub = registry.subscribe("living", "!room:matrix.test", "@user:matrix.test")
    assert sub.panel_id == "living"
    assert sub.expires_at == 1090.0
    assert registry.active_users("living") == ("@user:matrix.test",)

    clock.advance(30)
    assert registry.heartbeat("living", "@user:matrix.test") is True
    clock.advance(89)
    assert registry.active_users("living") == ("@user:matrix.test",)
    clock.advance(2)
    assert registry.active_users("living") == ()


def test_heartbeat_unknown_subscription_is_false():
    registry = WidgetSessionRegistry(now=lambda: 1.0)
    assert registry.heartbeat("missing", "@user:matrix.test") is False


def test_revision_is_monotonic_per_panel():
    registry = WidgetSessionRegistry(now=lambda: 1.0)
    assert registry.next_revision("living") == 1
    assert registry.next_revision("living") == 2
    assert registry.next_revision("garage") == 1


def test_request_id_is_single_use_until_replay_ttl_expires():
    clock = Clock()
    registry = WidgetSessionRegistry(now=clock, replay_ttl=120.0)
    assert registry.accept_request("living", "@user:matrix.test", "req-1") is True
    assert registry.accept_request("living", "@user:matrix.test", "req-1") is False
    clock.advance(121)
    assert registry.accept_request("living", "@user:matrix.test", "req-1") is True


def test_replay_memory_is_bounded_per_sender_panel():
    registry = WidgetSessionRegistry(now=lambda: 1.0, replay_limit=3)
    for request_id in ("a", "b", "c", "d"):
        assert registry.accept_request("living", "@user:matrix.test", request_id) is True
    assert registry.accept_request("living", "@user:matrix.test", "a") is True


def test_clear_panel_removes_sessions_revisions_and_replay_ids():
    registry = WidgetSessionRegistry(now=lambda: 1.0)
    registry.subscribe("living", "!room:matrix.test", "@user:matrix.test")
    assert registry.next_revision("living") == 1
    assert registry.accept_request("living", "@user:matrix.test", "req") is True

    registry.clear_panel("living")

    assert registry.active_users("living") == ()
    assert registry.next_revision("living") == 1
    assert registry.accept_request("living", "@user:matrix.test", "req") is True


def test_registry_exposes_no_persistence_api():
    registry = WidgetSessionRegistry(now=lambda: 1.0)
    assert not hasattr(registry, "dump")
    assert not hasattr(registry, "async_save")
