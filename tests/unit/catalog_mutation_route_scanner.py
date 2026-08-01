from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


@dataclass(frozen=True, slots=True)
class ScopedServiceCall:
    source: str
    owner: str
    transport: str
    entrypoint: str


def _service_calls(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call):
            continue
        if not isinstance(candidate.func, ast.Attribute):
            continue
        if not isinstance(candidate.func.value, ast.Name):
            continue
        class_name = candidate.func.value.id
        if class_name.endswith("Service"):
            calls.add(f"{class_name}.{candidate.func.attr}")
    return calls


def scan_route_service_calls(paths: Iterable[Path]) -> tuple[ScopedServiceCall, ...]:
    calls: list[ScopedServiceCall] = []
    for path in paths:
        tree = ast.parse(path.read_text())
        for handler in tree.body:
            if not isinstance(handler, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            methods = {
                decorator.func.attr.lower()
                for decorator in handler.decorator_list
                if isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "router"
                and decorator.func.attr.lower() in HTTP_METHODS
            }
            for method in methods:
                for entrypoint in _service_calls(handler):
                    calls.append(
                        ScopedServiceCall(
                            source=path.name,
                            owner=handler.name,
                            transport=method,
                            entrypoint=entrypoint,
                        )
                    )
    return tuple(calls)


def scan_command_service_calls(paths: Iterable[Path]) -> tuple[ScopedServiceCall, ...]:
    calls: list[ScopedServiceCall] = []
    for path in paths:
        tree = ast.parse(path.read_text())
        for entrypoint in _service_calls(tree):
            calls.append(
                ScopedServiceCall(
                    source=path.name,
                    owner="command",
                    transport="command",
                    entrypoint=entrypoint,
                )
            )
    return tuple(calls)


def unresolved_service_entrypoints(
    services_dir: Path,
    entrypoints: Iterable[str],
) -> set[str]:
    own_methods: dict[str, set[str]] = {}
    base_classes: dict[str, set[str]] = {}
    for path in services_dir.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            own_methods.setdefault(node.name, set()).update(
                child.name
                for child in node.body
                if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
            )
            base_classes.setdefault(node.name, set()).update(
                base.id for base in node.bases if isinstance(base, ast.Name)
            )

    def available_methods(class_name: str, seen: set[str] | None = None) -> set[str]:
        visited = {*seen} if seen else set()
        if class_name in visited:
            return set()
        visited.add(class_name)
        methods = set(own_methods.get(class_name, set()))
        for base_name in base_classes.get(class_name, set()):
            methods.update(available_methods(base_name, visited))
        return methods

    unresolved: set[str] = set()
    for entrypoint in entrypoints:
        class_name, method_name = entrypoint.split(".", 1)
        if method_name not in available_methods(class_name):
            unresolved.add(entrypoint)
    return unresolved
