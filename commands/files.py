from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class FileCommands:
    """File and folder operations for the assistant."""

    def create_folder(self, path: str) -> str:
        Path(path).mkdir(parents=True, exist_ok=True)
        return f"Created folder at {path}."

    def delete_folder(self, path: str) -> str:
        if not Path(path).exists():
            return f"Folder not found: {path}"
        shutil.rmtree(path)
        return f"Deleted folder at {path}."

    def rename_folder(self, old_path: str, new_path: str) -> str:
        os.rename(old_path, new_path)
        return f"Renamed folder to {new_path}."

    def move_folder(self, source: str, destination: str) -> str:
        shutil.move(source, destination)
        return f"Moved folder to {destination}."

    def copy_folder(self, source: str, destination: str) -> str:
        shutil.copytree(source, destination)
        return f"Copied folder to {destination}."

    def create_file(self, path: str) -> str:
        Path(path).touch(exist_ok=True)
        return f"Created file at {path}."

    def delete_file(self, path: str) -> str:
        if not Path(path).exists():
            return f"File not found: {path}"
        Path(path).unlink()
        return f"Deleted file at {path}."

    def rename_file(self, old_path: str, new_path: str) -> str:
        os.rename(old_path, new_path)
        return f"Renamed file to {new_path}."

    def move_file(self, source: str, destination: str) -> str:
        shutil.move(source, destination)
        return f"Moved file to {destination}."

    def copy_file(self, source: str, destination: str) -> str:
        shutil.copy2(source, destination)
        return f"Copied file to {destination}."

    def open_folder(self, folder: str) -> str:
        folders = {
            "downloads": str(Path.home() / "Downloads"),
            "desktop": str(Path.home() / "Desktop"),
            "documents": str(Path.home() / "Documents"),
            "pictures": str(Path.home() / "Pictures"),
            "videos": str(Path.home() / "Videos"),
        }
        target = folders.get(folder.lower())
        if not target:
            return f"I don't recognize the folder {folder}."
        subprocess.Popen(["explorer.exe", target])
        return f"Opened {folder}."

    def search_files(self, query: str) -> str:
        matches = []
        for path in Path.home().rglob("*"):
            if query.lower() in path.name.lower():
                matches.append(str(path))
        if not matches:
            return f"No files found for {query}."
        return "\n".join(matches[:10])
