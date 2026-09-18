from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
RENDER = COMP / "control_panel_render.py"
PANELS = COMP / "control_panels.py"
SAFE_ACTIONS = COMP / "safe_actions.py"


def load_modules():
    assert RENDER.exists(), "control_panel_render.py is not implemented yet"
    pkg_name = "matrix_extended_control_panel_render_v060_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package

    def load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(f"{pkg_name}.{name}", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    load("safe_actions", SAFE_ACTIONS)
    panels = load("control_panels", PANELS)
    render = load("control_panel_render", RENDER)
    return render, panels


def state(value: str, **attrs):
    return types.SimpleNamespace(state=value, attributes=attrs)


def make_panel(panels, *, title="🏠 Garage"):
    return panels.ControlPanelDefinition(
        panel_id="garage",
        room_id="!room:test",
        title=title,
        enabled=True,
        entities=(
            panels.PanelEntity("light.garage", "Light"),
            panels.PanelEntity("cover.garage", "Gate"),
            panels.PanelEntity("alarm_control_panel.home", "Alarm"),
            panels.PanelEntity("climate.garage", "Climate"),
            panels.PanelEntity("sensor.garage_temperature", "Temperature"),
            panels.PanelEntity("custom.thing", "Mystery"),
        ),
        actions=(),
        allowed_users=(),
        debounce=1.5,
    )


def test_render_maps_common_ha_domains_and_units() -> None:
    render, panels = load_modules()
    panel = make_panel(panels)
    states = {
        "light.garage": state("on"),
        "cover.garage": state("opening"),
        "alarm_control_panel.home": state("armed_away"),
        "climate.garage": state(
            "heat",
            current_temperature=18.5,
            temperature=21,
            temperature_unit="°C",
        ),
        "sensor.garage_temperature": state("18.7", unit_of_measurement="°C"),
        "custom.thing": state("raw_state"),
    }

    rendered = render.render_control_panel(panel, states)

    assert rendered.body.splitlines() == [
        "🏠 Garage",
        "",
        "Light: On",
        "Gate: Opening",
        "Alarm: Armed away",
        "Climate: Heat · 18.5 °C → 21 °C",
        "Temperature: 18.7 °C",
        "Mystery: raw_state",
    ]


def test_render_handles_off_closed_disarmed_and_missing() -> None:
    render, panels = load_modules()
    panel = panels.ControlPanelDefinition(
        panel_id="simple",
        room_id="!room:test",
        title="Simple",
        enabled=True,
        entities=(
            panels.PanelEntity("light.one", "Light"),
            panels.PanelEntity("cover.one", "Door"),
            panels.PanelEntity("alarm_control_panel.one", "Alarm"),
            panels.PanelEntity("sensor.missing", "Missing"),
        ),
        actions=(),
        allowed_users=(),
        debounce=1.5,
    )

    rendered = render.render_control_panel(
        panel,
        {
            "light.one": state("off"),
            "cover.one": state("closed"),
            "alarm_control_panel.one": state("disarmed"),
        },
    )

    assert "Light: Off" in rendered.body
    assert "Door: Closed" in rendered.body
    assert "Alarm: Disarmed" in rendered.body
    assert "Missing: unavailable" in rendered.body


def test_render_preserves_config_order_and_action_legend() -> None:
    render, panels = load_modules()
    safe_actions = sys.modules[
        "matrix_extended_control_panel_render_v060_testpkg.safe_actions"
    ]
    panel = panels.ControlPanelDefinition(
        panel_id="garage",
        room_id="!room:test",
        title="Garage",
        enabled=True,
        entities=(
            panels.PanelEntity("sensor.second", "Second"),
            panels.PanelEntity("sensor.first", "First"),
        ),
        actions=(
            panels.PanelAction(
                "open",
                "🔼",
                "Open",
                safe_actions.SafeActionDefinition(
                    "open",
                    safe_actions.ServiceActionHandler(
                        "cover.open_cover", {"entity_id": "cover.garage"}, {}
                    ),
                ),
            ),
            panels.PanelAction(
                "close",
                "🔽",
                "Close",
                safe_actions.SafeActionDefinition(
                    "close",
                    safe_actions.ServiceActionHandler(
                        "cover.close_cover", {"entity_id": "cover.garage"}, {}
                    ),
                ),
            ),
        ),
        allowed_users=(),
        debounce=1.5,
    )

    rendered = render.render_control_panel(
        panel,
        {
            "sensor.first": state("1"),
            "sensor.second": state("2"),
        },
    )

    assert rendered.body.index("Second: 2") < rendered.body.index("First: 1")
    assert rendered.body.endswith("Control:\n🔼 Open · 🔽 Close")


def test_html_escapes_user_text_but_plain_body_does_not() -> None:
    render, panels = load_modules()
    panel = panels.ControlPanelDefinition(
        panel_id="escape",
        room_id="!room:test",
        title="<Garage & Home>",
        enabled=True,
        entities=(panels.PanelEntity("sensor.x", "<Temp>"),),
        actions=(),
        allowed_users=(),
        debounce=1.5,
    )

    rendered = render.render_control_panel(
        panel,
        {"sensor.x": state("<unsafe>", unit_of_measurement="°C")},
    )

    assert "<Garage & Home>" in rendered.body
    assert "<Temp>: <unsafe> °C" in rendered.body
    assert "&lt;Garage &amp; Home&gt;" in rendered.formatted_body
    assert "&lt;Temp&gt;" in rendered.formatted_body
    assert "&lt;unsafe&gt;" in rendered.formatted_body
    assert "<unsafe>" not in rendered.formatted_body


def test_digest_is_stable_and_changes_only_with_rendered_content() -> None:
    render, panels = load_modules()
    panel = make_panel(panels)
    states = {
        entity.entity_id: state("off")
        for entity in panel.entities
    }

    first = render.render_control_panel(panel, states)
    second = render.render_control_panel(panel, states)
    changed = dict(states)
    changed["light.garage"] = state("on")
    third = render.render_control_panel(panel, changed)

    assert first.body == second.body
    assert first.formatted_body == second.formatted_body
    assert first.digest == second.digest
    assert len(first.digest) == 64
    assert third.digest != first.digest
    assert "Updated:" not in first.body
