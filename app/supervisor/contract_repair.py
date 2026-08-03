from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterable


_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_STATUS_CONSTANTS = {
    "HTTP_200_OK": 200,
    "HTTP_201_CREATED": 201,
    "HTTP_202_ACCEPTED": 202,
    "HTTP_204_NO_CONTENT": 204,
    "HTTP_400_BAD_REQUEST": 400,
    "HTTP_401_UNAUTHORIZED": 401,
    "HTTP_403_FORBIDDEN": 403,
    "HTTP_404_NOT_FOUND": 404,
    "HTTP_409_CONFLICT": 409,
    "HTTP_422_UNPROCESSABLE_ENTITY": 422,
}


@dataclass(frozen=True)
class FastAPIStatusRepair:
    path: str
    content: str
    changes: tuple[str, ...]
    strategy_key: str


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for index, character in enumerate(text):
        if character == "\n":
            offsets.append(index + 1)
    return offsets


def _absolute_offset(offsets: list[int], line: int, column: int) -> int:
    return offsets[line - 1] + column


def _route_call(expression: ast.AST) -> tuple[str, str] | None:
    if not isinstance(expression, ast.Call):
        return None
    function = expression.func
    if not isinstance(function, ast.Attribute):
        return None
    method = function.attr.casefold()
    if method not in _HTTP_METHODS or not expression.args:
        return None
    route = expression.args[0]
    if not isinstance(route, ast.Constant) or not isinstance(route.value, str):
        return None
    return method, route.value


def _status_expression_route(
    expression: ast.AST,
    assignments: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    if not isinstance(expression, ast.Attribute) or expression.attr != "status_code":
        return None
    value = expression.value
    if isinstance(value, ast.Name):
        return assignments.get(value.id)
    return _route_call(value)


def _integer_constant(expression: ast.AST) -> int | None:
    if (
        isinstance(expression, ast.Constant)
        and isinstance(expression.value, int)
        and not isinstance(expression.value, bool)
    ):
        return expression.value
    return None


def _contracts_from_test(source: str) -> dict[tuple[str, str], set[int]]:
    tree = ast.parse(source)
    contracts: dict[tuple[str, str], set[int]] = {}

    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assignments: dict[str, tuple[str, str]] = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign):
                route = _route_call(node.value)
                if route is None:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments[target.id] = route
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                route = _route_call(node.value)
                if route is not None and isinstance(node.target, ast.Name):
                    assignments[node.target.id] = route

        for node in ast.walk(scope):
            if not isinstance(node, ast.Assert):
                continue
            comparison = node.test
            if not isinstance(comparison, ast.Compare) or len(comparison.ops) != 1:
                continue
            if not isinstance(comparison.ops[0], ast.Eq):
                continue
            left = comparison.left
            right = comparison.comparators[0]
            left_route = _status_expression_route(left, assignments)
            right_route = _status_expression_route(right, assignments)
            left_status = _integer_constant(left)
            right_status = _integer_constant(right)
            route: tuple[str, str] | None = None
            expected: int | None = None
            if left_route is not None and right_status is not None:
                route, expected = left_route, right_status
            elif right_route is not None and left_status is not None:
                route, expected = right_route, left_status
            if route is not None and expected is not None:
                contracts.setdefault(route, set()).add(expected)
    return contracts


def _decorator_status(call: ast.Call) -> tuple[int | None, ast.keyword | None, bool]:
    keyword = next(
        (item for item in call.keywords if item.arg == "status_code"),
        None,
    )
    if keyword is None:
        return 200, None, True
    value = keyword.value
    literal = _integer_constant(value)
    if literal is not None:
        return literal, keyword, True
    if isinstance(value, ast.Attribute):
        mapped = _STATUS_CONSTANTS.get(value.attr)
        if mapped is not None:
            return mapped, keyword, True
    return None, keyword, False


def build_fastapi_status_code_repair(
    *,
    target_path: str,
    target_source: str,
    contract_sources: Iterable[str],
    failure_output: str,
) -> FastAPIStatusRepair | None:
    """Build one safe, deterministic FastAPI decorator status repair.

    The repair activates only when pytest evidence explicitly mentions a
    ``status_code`` assertion and the protected/read-only contract sources
    unambiguously describe the expected HTTP status for a route.
    """

    folded_output = failure_output.casefold()
    if "status_code" not in folded_output or "assert" not in folded_output:
        return None
    if not target_path.casefold().endswith(".py"):
        return None

    contracts: dict[tuple[str, str], set[int]] = {}
    try:
        for source in contract_sources:
            for route, statuses in _contracts_from_test(source).items():
                contracts.setdefault(route, set()).update(statuses)
        tree = ast.parse(target_source)
    except (SyntaxError, ValueError):
        return None

    expected_by_route = {
        route: next(iter(statuses))
        for route, statuses in contracts.items()
        if len(statuses) == 1
    }
    if not expected_by_route:
        return None

    offsets = _line_offsets(target_source)
    edits: list[tuple[int, int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            route = _route_call(decorator)
            if route is None or route not in expected_by_route:
                continue
            assert isinstance(decorator, ast.Call)
            expected = expected_by_route[route]
            actual, keyword, supported = _decorator_status(decorator)
            if not supported or actual == expected:
                continue
            method, path = route
            change = f"{method.upper()} {path}: {actual} -> {expected}"
            if keyword is None:
                if decorator.end_lineno is None or decorator.end_col_offset is None:
                    return None
                end = _absolute_offset(
                    offsets,
                    decorator.end_lineno,
                    decorator.end_col_offset,
                )
                insert_at = end - 1
                if insert_at < 0 or target_source[insert_at:end] != ")":
                    return None
                edits.append(
                    (
                        insert_at,
                        insert_at,
                        f", status_code={expected}",
                        change,
                    )
                )
            else:
                value = keyword.value
                if (
                    value.lineno is None
                    or value.col_offset is None
                    or value.end_lineno is None
                    or value.end_col_offset is None
                ):
                    return None
                start = _absolute_offset(offsets, value.lineno, value.col_offset)
                end = _absolute_offset(
                    offsets,
                    value.end_lineno,
                    value.end_col_offset,
                )
                edits.append((start, end, str(expected), change))

    if not edits:
        return None

    repaired = target_source
    for start, end, replacement, _change in sorted(
        edits,
        key=lambda item: item[0],
        reverse=True,
    ):
        repaired = repaired[:start] + replacement + repaired[end:]
    try:
        ast.parse(repaired)
    except SyntaxError:
        return None
    if repaired == target_source:
        return None

    changes = tuple(item[3] for item in edits)
    strategy_suffix = "|".join(sorted(changes))
    return FastAPIStatusRepair(
        path=target_path,
        content=repaired,
        changes=changes,
        strategy_key=f"fastapi_status_contract:{target_path}:{strategy_suffix}",
    )
