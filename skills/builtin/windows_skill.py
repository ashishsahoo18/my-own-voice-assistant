"""Windows desktop and system automation skill for OLIVER 2.0."""

from __future__ import annotations

from typing import Any
from commands.windows import WindowsCommands
from commands.system import SystemCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class WindowsSkill(BaseSkill):
    """Adapter wrapping Windows desktop automation commands."""

    def __init__(self) -> None:
        super().__init__()
        self.windows = WindowsCommands()
        self.system = SystemCommands()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="windows",
            version="1.0.0",
            description="Control Windows applications, audio volume, workstation state, and power commands.",
            triggers=[
                "open notepad", "launch calculator", "open vs code",
                "lock computer", "volume up", "volume down", "mute",
                "shutdown", "restart", "sleep", "restart explorer",
            ],
            required_permissions=["os.launch", "os.power"],
            dependencies=["psutil", "pywin32"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="windows.open_app",
                description="Launch a desktop application, control panel, or settings utility by name.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.open_app,
            ),
            ToolSpec(
                name="windows.lock_computer",
                description="Lock the Windows workstation.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.lock_computer,
            ),
            ToolSpec(
                name="windows.restart_explorer",
                description="Restart Windows Explorer process.",
                risk_level=ToolRiskLevel.SENSITIVE,
                handler=self.restart_explorer,
            ),
            ToolSpec(
                name="windows.volume_up",
                description="Increase master audio volume.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.volume_up,
            ),
            ToolSpec(
                name="windows.volume_down",
                description="Decrease master audio volume.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.volume_down,
            ),
            ToolSpec(
                name="windows.mute",
                description="Mute master audio volume.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.mute,
            ),
            ToolSpec(
                name="windows.shutdown",
                description="Power down the computer workstation.",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.shutdown,
            ),
            ToolSpec(
                name="windows.restart",
                description="Reboot the computer workstation.",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.restart,
            ),
            ToolSpec(
                name="windows.sleep",
                description="Put the workstation to sleep mode.",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.sleep,
            ),
        ]

    def open_app(self, app_name: str) -> ToolResult:
        res = self.windows.open_app(app_name)
        if res.startswith("I do not support"):
            # Try system fallback
            res = self.system.open_app(app_name)
        return ToolResult(status="SUCCESS", message=res, data={"app_name": app_name})

    def lock_computer(self) -> ToolResult:
        res = self.windows.lock_computer()
        return ToolResult(status="SUCCESS", message=res)

    def restart_explorer(self) -> ToolResult:
        res = self.windows.restart_explorer()
        return ToolResult(status="SUCCESS", message=res)

    def volume_up(self) -> ToolResult:
        res = self.system.volume_up()
        return ToolResult(status="SUCCESS", message=res)

    def volume_down(self) -> ToolResult:
        res = self.system.volume_down()
        return ToolResult(status="SUCCESS", message=res)

    def mute(self) -> ToolResult:
        res = self.system.mute()
        return ToolResult(status="SUCCESS", message=res)

    def shutdown(self) -> ToolResult:
        res = self.system.shutdown()
        return ToolResult(status="SUCCESS", message=res)

    def restart(self) -> ToolResult:
        res = self.system.restart()
        return ToolResult(status="SUCCESS", message=res)

    def sleep(self) -> ToolResult:
        res = self.system.sleep()
        return ToolResult(status="SUCCESS", message=res)
