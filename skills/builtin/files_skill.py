"""File and folder management skill for OLIVER 2.0."""

from __future__ import annotations

from commands.files import FileCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class FilesSkill(BaseSkill):
    """Adapter wrapping filesystem management commands."""

    def __init__(self) -> None:
        super().__init__()
        self.files = FileCommands()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="files",
            version="1.0.0",
            description="Manage files, folders, directories, copies, and moves.",
            triggers=["create folder", "create file", "list files", "open folder", "rename file", "copy file"],
            dependencies=["shutil", "pathlib"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="files.create_folder",
                description="Create a directory or folder at the specified path.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.create_folder,
            ),
            ToolSpec(
                name="files.create_file",
                description="Create a new empty file at the specified path.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.create_file,
            ),
            ToolSpec(
                name="files.list_folder",
                description="List files inside a folder.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.list_folder,
            ),
            ToolSpec(
                name="files.open_folder",
                description="Open a folder in Windows Explorer.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.open_folder,
            ),
            ToolSpec(
                name="files.move_file",
                description="Move a file or folder from source to destination.",
                risk_level=ToolRiskLevel.SENSITIVE,
                handler=self.move_file,
            ),
            ToolSpec(
                name="files.copy_file",
                description="Copy a file or folder from source to destination.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.copy_file,
            ),
            ToolSpec(
                name="files.rename_file",
                description="Rename an existing file or folder.",
                risk_level=ToolRiskLevel.SENSITIVE,
                handler=self.rename_file,
            ),
            ToolSpec(
                name="files.delete_file",
                description="Delete a file (requires user confirmation).",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.delete_file,
            ),
            ToolSpec(
                name="files.delete_folder",
                description="Delete a folder (requires user confirmation).",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.delete_folder,
            ),
        ]

    def create_folder(self, path: str) -> ToolResult:
        res = self.files.create_folder(path)
        return ToolResult(status="SUCCESS", message=res, data={"path": path})

    def create_file(self, path: str) -> ToolResult:
        res = self.files.create_file(path)
        return ToolResult(status="SUCCESS", message=res, data={"path": path})

    def list_folder(self, path: str = "") -> ToolResult:
        res = self.files.list_folder(path)
        return ToolResult(status="SUCCESS", message=res, data={"path": path})

    def open_folder(self, path: str) -> ToolResult:
        res = self.files.open_folder(path)
        return ToolResult(status="SUCCESS", message=res, data={"path": path})

    def move_file(self, source: str, destination: str) -> ToolResult:
        res = self.files.move_file(source, destination)
        return ToolResult(status="SUCCESS", message=res)

    def copy_file(self, source: str, destination: str) -> ToolResult:
        res = self.files.copy_file(source, destination)
        return ToolResult(status="SUCCESS", message=res)

    def rename_file(self, old_path: str, new_path: str) -> ToolResult:
        res = self.files.rename_file(old_path, new_path)
        return ToolResult(status="SUCCESS", message=res)

    def delete_file(self, path: str) -> ToolResult:
        res = self.files.delete_file(path)
        return ToolResult(status="SUCCESS", message=res)

    def delete_folder(self, path: str) -> ToolResult:
        res = self.files.delete_folder(path)
        return ToolResult(status="SUCCESS", message=res)
