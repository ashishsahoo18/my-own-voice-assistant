"""Productivity, reminders, timers, and safe math calculation skill for OLIVER 2.0."""

from __future__ import annotations

import ast
import operator
from typing import Optional
from commands.productivity import ProductivityCommands
from commands.reminders import ReminderCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec

# Safe arithmetic operators mapping
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


def safe_eval_math(expr: str) -> float | int:
    """Safely evaluate mathematical expressions using AST without eval()."""
    def _eval(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
            left = _eval(node.left)
            right = _eval(node.right)
            return SAFE_OPERATORS[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
            operand = _eval(node.operand)
            return SAFE_OPERATORS[type(node.op)](operand)
        raise ValueError(f"Unsupported math syntax: {ast.dump(node)}")

    tree = ast.parse(expr.strip(), mode="eval")
    return _eval(tree)


class ProductivitySkill(BaseSkill):
    """Adapter wrapping reminders, safe math calculation, and timer controls."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        super().__init__()
        self.reminders = ReminderCommands(db_path)
        self.productivity = ProductivityCommands()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="productivity",
            version="1.0.0",
            description="Manage reminders, timers, stopwatch, and safe mathematical calculations.",
            triggers=["calculate", "remind me", "show reminders", "start stopwatch", "start countdown"],
            dependencies=["sqlite3"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="productivity.calculate",
                description="Safely evaluate a mathematical calculation without eval.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.calculate,
            ),
            ToolSpec(
                name="productivity.add_reminder",
                description="Save a new reminder with optional time.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.add_reminder,
            ),
            ToolSpec(
                name="productivity.list_reminders",
                description="List saved pending reminders.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.list_reminders,
            ),
            ToolSpec(
                name="productivity.start_stopwatch",
                description="Start a stopwatch timer.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.start_stopwatch,
            ),
            ToolSpec(
                name="productivity.stop_stopwatch",
                description="Stop the active stopwatch timer.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.stop_stopwatch,
            ),
            ToolSpec(
                name="productivity.start_countdown",
                description="Start a background countdown for N seconds.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.start_countdown,
            ),
        ]

    def calculate(self, expression: str) -> ToolResult:
        try:
            val = safe_eval_math(expression)
            return ToolResult(status="SUCCESS", message=f"Result: {val}", data={"result": val})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Calculation error: {exc}", error=str(exc))

    def add_reminder(self, title: str, remind_at: Optional[str] = None) -> ToolResult:
        res = self.reminders.add_reminder(title, remind_at)
        return ToolResult(status="SUCCESS", message=res, data={"title": title})

    def list_reminders(self) -> ToolResult:
        res = self.reminders.list_reminders()
        return ToolResult(status="SUCCESS", message=res)

    def start_stopwatch(self) -> ToolResult:
        res = self.productivity.start_stopwatch()
        return ToolResult(status="SUCCESS", message=res)

    def stop_stopwatch(self) -> ToolResult:
        res = self.productivity.stop_stopwatch()
        return ToolResult(status="SUCCESS", message=res)

    def start_countdown(self, seconds: int) -> ToolResult:
        res = self.productivity.start_countdown(seconds)
        return ToolResult(status="SUCCESS", message=res, data={"seconds": seconds})
