from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
CLIENT_PATH = ROOT / "custom_components" / "matrix_extended" / "client.py"


def test_matrix_nio_timeout_retries_are_bounded() -> None:
    """Override nio's unlimited timeout retries so HA can expose disconnects."""
    tree = ast.parse(CLIENT_PATH.read_text())
    configs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AsyncClientConfig"
    ]
    assert len(configs) == 1
    values = {kw.arg: kw.value for kw in configs[0].keywords if kw.arg is not None}
    assert "max_timeouts" in values
    assert isinstance(values["max_timeouts"], ast.Constant)
    assert values["max_timeouts"].value == 0
