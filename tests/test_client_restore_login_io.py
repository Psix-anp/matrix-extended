from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
CLIENT_PATH = ROOT / "custom_components" / "matrix_extended" / "client.py"


def _method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return item
    raise AssertionError(f"{class_name}.{method_name} not found")


def _calls_attribute(node: ast.AST, attribute: str) -> bool:
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and item.func.attr == attribute
        for item in ast.walk(node)
    )


def test_restore_login_is_not_run_in_synchronous_constructor() -> None:
    """matrix-nio store loading must not block Home Assistant's event loop."""
    tree = ast.parse(CLIENT_PATH.read_text())
    constructor = _method(tree, "MatrixClient", "__init__")
    assert not _calls_attribute(constructor, "restore_login")


def test_async_connect_offloads_restore_login() -> None:
    """Persistent nio store loading must run in a worker thread before I/O starts."""
    tree = ast.parse(CLIENT_PATH.read_text())
    connect = _method(tree, "MatrixClient", "async_connect")
    assert any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and isinstance(item.func.value, ast.Name)
        and item.func.value.id == "asyncio"
        and item.func.attr == "to_thread"
        for item in ast.walk(connect)
    )
