class Calculator:
    """Minimal calculator helper for expressions."""

    def evaluate(self, expression: str) -> str:
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return f"{result}"
        except Exception as exc:
            return f"Error: {exc}"
