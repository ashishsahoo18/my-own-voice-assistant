# Writing a Skill for OLIVER 2.0

This guide explains how to build and register new skills and tools in OLIVER 2.0.

---

## 1. Skill Contract Overview

Every skill in OLIVER 2.0 inherits from `skills.base.BaseSkill` and defines two mandatory methods:
1. `get_manifest()`: Declares metadata, triggers, required permissions, and dependencies.
2. `get_tools()`: Declares executable tools (`ToolSpec`) with their risk levels and handlers.

```python
from skills.base import BaseSkill, SkillManifest, ToolSpec, ToolResult, ToolRiskLevel

class MyCustomSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="custom_skill",
            version="1.0.0",
            description="Performs custom actions.",
            triggers=["run custom action", "do something"],
            required_permissions=[],
            dependencies=[],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="custom_skill.do_something",
                description="Execute custom action.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.do_something,
            )
        ]

    def do_something(self, argument: str = "") -> ToolResult:
        # Business logic here
        return ToolResult(
            status="SUCCESS",
            message=f"Action completed with: {argument}",
            data={"result": argument},
        )
```

---

## 2. Risk Levels

Every tool declares a `ToolRiskLevel`:
- `ToolRiskLevel.SAFE (0)`: Read-only operations, web navigation, information lookups. Auto-executed.
- `ToolRiskLevel.LOW (1)`: Creating non-critical notes, opening apps, taking screenshots. Auto-executed, logged.
- `ToolRiskLevel.SENSITIVE (2)`: Sending emails, WhatsApp messages, moving/renaming files. Explicit user confirmation required.
- `ToolRiskLevel.DANGEROUS (3)`: Workstation shutdown, restarting, deleting files/folders, credential access. Explicit confirmation required with exact action preview.

---

## 3. ToolResult Contract

Tool handlers must return a `ToolResult` containing:
- `status`: `"SUCCESS"`, `"VERIFIED"`, `"UNVERIFIED"`, `"FAILED"`, `"DENIED"`, `"CANCELLED"`, `"TIMEOUT"`.
- `message`: User-friendly human/spoken response.
- `data`: Structured dictionary of output data.
- `evidence`: Verification evidence (e.g. process ID, file size, response code).
- `error`: Error string if failed.

---

## 4. Registering a Skill

### Programmatic Registration
```python
from skills.registry import get_registry
from my_skill import MyCustomSkill

registry = get_registry()
registry.register(MyCustomSkill())
```

### Drop-in User Skills
Place a skill package in the `user_skills/` directory with an `__init__.py` exposing a `get_skill() -> BaseSkill` function. OLIVER auto-discovers and registers valid drop-in skills on startup.

---

## 5. Health Checks and Broken Skill Isolation

Skills can implement `health_check() -> tuple[bool, str]`. If a required dependency is missing or a service is down:
- Return `(False, "Missing dependency: XYZ")`.
- The SkillRegistry will register the skill as **disabled**, log the reason, and allow OLIVER to boot cleanly without crashing.
