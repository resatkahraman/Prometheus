import ast
from typing import Any

import sympy as sp

from app.tools.base import BaseTool, ToolError


_ALLOWED_FUNCTIONS = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sqrt": sp.sqrt,
    "log": sp.log,
    "exp": sp.exp,
    "abs": sp.Abs,
}

_ALLOWED_CONSTANTS = {
    "pi": sp.pi,
    "e": sp.E,
}


class _SafeSympyParser:
    def __init__(self) -> None:
        self.symbols: dict[str, sp.Symbol] = {}

    def parse(self, expression: str) -> sp.Expr:
        if len(expression) > 1_000:
            raise ToolError("Sembolik ifade çok uzun.")
        try:
            node = ast.parse(expression, mode="eval").body
        except SyntaxError as exc:
            raise ToolError(f"Geçersiz matematik ifadesi: {exc.msg}") from exc
        return self._eval(node)

    def _eval(self, node: ast.AST) -> sp.Expr:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(
                node.value,
                (int, float),
            ):
                raise ToolError("Yalnızca sayısal sabitler desteklenir.")
            return sp.sympify(node.value)

        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_CONSTANTS:
                return _ALLOWED_CONSTANTS[node.id]
            if not node.id.isidentifier() or node.id.startswith("_"):
                raise ToolError(f"Geçersiz sembol: {node.id}")
            return self.symbols.setdefault(node.id, sp.Symbol(node.id))

        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
            raise ToolError("Desteklenmeyen tekli işlem.")

        if isinstance(node, ast.BinOp):
            left = self._eval(node.left)
            right = self._eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                if right.is_number and abs(float(right)) > 100:
                    raise ToolError("Üs güvenlik sınırını aşıyor.")
                return left**right
            if isinstance(node.op, ast.Mod):
                return sp.Mod(left, right)
            raise ToolError("Desteklenmeyen ikili işlem.")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ToolError("Desteklenmeyen fonksiyon çağrısı.")
            function = _ALLOWED_FUNCTIONS.get(node.func.id)
            if function is None:
                raise ToolError(f"Desteklenmeyen fonksiyon: {node.func.id}")
            if node.keywords:
                raise ToolError("Anahtar kelimeli argüman desteklenmiyor.")
            arguments = [self._eval(argument) for argument in node.args]
            if len(arguments) > 3:
                raise ToolError("Çok fazla fonksiyon argümanı.")
            return function(*arguments)

        raise ToolError(f"Desteklenmeyen ifade türü: {type(node).__name__}")


class SymbolicMathTool(BaseTool):
    name = "symbolic_math"
    description = (
        "SymPy tabanlı güvenli sembolik hesap yapar: simplify, evaluate, "
        "differentiate, integrate ve solve."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "simplify",
                    "evaluate",
                    "differentiate",
                    "integrate",
                    "solve",
                ],
            },
            "expression": {
                "type": "string",
                "description": "Python matematik sözdizimi: x**2, sin(x), sqrt(2).",
            },
            "variable": {"type": "string"},
            "substitutions": {
                "type": "object",
                "additionalProperties": {
                    "type": ["number", "string"],
                },
            },
        },
        "required": ["operation", "expression"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        operation = arguments.get("operation")
        expression_text = arguments.get("expression")
        if operation not in {
            "simplify",
            "evaluate",
            "differentiate",
            "integrate",
            "solve",
        }:
            raise ToolError("Desteklenmeyen symbolic_math operation.")
        if not isinstance(expression_text, str) or not expression_text.strip():
            raise ToolError("'expression' zorunludur.")

        parser = _SafeSympyParser()
        expression = parser.parse(expression_text)

        substitutions = arguments.get("substitutions", {})
        if substitutions is None:
            substitutions = {}
        if not isinstance(substitutions, dict):
            raise ToolError("'substitutions' JSON nesnesi olmalıdır.")

        substitution_map: dict[sp.Symbol, sp.Expr] = {}
        for name, value in substitutions.items():
            if not isinstance(name, str) or not name.isidentifier():
                raise ToolError(f"Geçersiz substitution sembolü: {name}")
            symbol = parser.symbols.setdefault(name, sp.Symbol(name))
            if isinstance(value, (int, float)):
                substitution_map[symbol] = sp.sympify(value)
            elif isinstance(value, str):
                substitution_map[symbol] = _SafeSympyParser().parse(value)
            else:
                raise ToolError("Substitution değeri sayı veya metin olmalıdır.")

        if substitution_map:
            expression = expression.subs(substitution_map)

        variable_name = arguments.get("variable")
        variable: sp.Symbol | None = None
        if variable_name is not None:
            if not isinstance(variable_name, str) or not variable_name.isidentifier():
                raise ToolError("'variable' geçerli bir sembol olmalıdır.")
            variable = parser.symbols.setdefault(
                variable_name,
                sp.Symbol(variable_name),
            )

        if operation == "simplify":
            result = sp.simplify(expression)
        elif operation == "evaluate":
            result = sp.N(expression, 15)
        elif operation == "differentiate":
            if variable is None:
                raise ToolError("differentiate için 'variable' zorunludur.")
            result = sp.diff(expression, variable)
        elif operation == "integrate":
            if variable is None:
                raise ToolError("integrate için 'variable' zorunludur.")
            result = sp.integrate(expression, variable)
        else:
            if variable is None:
                raise ToolError("solve için 'variable' zorunludur.")
            result = sp.solve(expression, variable)

        return {
            "operation": operation,
            "expression": str(expression),
            "result": str(result),
            "latex": sp.latex(result),
            "free_symbols": sorted(str(item) for item in expression.free_symbols),
        }
