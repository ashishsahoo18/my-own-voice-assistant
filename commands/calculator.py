"""Safe calculator helper using AST-based parsing without eval()."""

import ast
import operator

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return safe_eval(node.body)
    elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
        left = safe_eval(node.left)
        right = safe_eval(node.right)
        return SAFE_OPERATORS[type(node.op)](left, right)
    elif isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
        operand = safe_eval(node.operand)
        return SAFE_OPERATORS[type(node.op)](operand)
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


class Calculator:
    """Safe calculator helper for mathematical expressions."""

    def evaluate(self, expression: str) -> str:
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            result = safe_eval(tree)
            return f"{result}"
        except Exception as exc:
            return f"Error: {exc}"
