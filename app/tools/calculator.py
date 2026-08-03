import ast
import math
import operator
from typing import Any

from app.tools.base import BaseTool, ToolError


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CONSTANTS = {"pi": math.pi, "e": math.e}
_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
}


class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "Güvenli matematik hesaplamaları yapar. Toplama, çıkarma, çarpma, "
        "bölme, üs, mod, parantez ve sınırlı matematik fonksiyonlarını destekler."
    )
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Hesaplanacak matematik ifadesi.",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        expression = arguments.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ToolError("'expression' dolu bir metin olmalıdır.")
        if len(expression) > 500:
            raise ToolError("Matematik ifadesi çok uzun.")
        try:
            result = self._evaluate(ast.parse(expression, mode="eval").body)
        except (SyntaxError, ValueError, TypeError, ZeroDivisionError) as exc:
            raise ToolError(f"İfade hesaplanamadı: {exc}") from exc
        if isinstance(result, complex):
            raise ToolError("Karmaşık sayı sonucu desteklenmiyor.")
        if isinstance(result, float) and not math.isfinite(result):
            raise ToolError("Sonuç sonlu bir sayı değil.")
        if abs(float(result)) > 1e100:
            raise ToolError("Sonuç güvenlik sınırını aşıyor.")
        return {"expression": expression, "result": result}

    def _evaluate(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ToolError("Yalnızca sayısal sabitler desteklenir.")
            return node.value
        if isinstance(node, ast.Name):
            if node.id in _CONSTANTS:
                return _CONSTANTS[node.id]
            raise ToolError(f"Bilinmeyen sabit: {node.id}")
        if isinstance(node, ast.BinOp):
            operation = _BINARY_OPERATORS.get(type(node.op))
            if operation is None:
                raise ToolError("Desteklenmeyen işlem.")
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(float(right)) > 20:
                raise ToolError("Üs değeri güvenlik sınırını aşıyor.")
            return operation(left, right)
        if isinstance(node, ast.UnaryOp):
            operation = _UNARY_OPERATORS.get(type(node.op))
            if operation is None:
                raise ToolError("Desteklenmeyen tekli işlem.")
            return operation(self._evaluate(node.operand))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ToolError("Desteklenmeyen fonksiyon çağrısı.")
            function = _FUNCTIONS.get(node.func.id)
            if function is None:
                raise ToolError(f"Desteklenmeyen fonksiyon: {node.func.id}")
            if node.keywords:
                raise ToolError("Anahtar kelimeli argüman desteklenmiyor.")
            values = [self._evaluate(argument) for argument in node.args]
            if len(values) > 3:
                raise ToolError("Çok fazla fonksiyon argümanı.")
            return function(*values)
        raise ToolError(f"Desteklenmeyen ifade türü: {type(node).__name__}")
