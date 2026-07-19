"""File and folder commands for AYRA AI."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class FileCommands:
    """File and folder operations for the assistant."""

    def __init__(self) -> None:
        self.known_folders = {
            "downloads": Path.home() / "Downloads",
            "desktop": Path.home() / "Desktop",
            "documents": Path.home() / "Documents",
            "pictures": Path.home() / "Pictures",
            "videos": Path.home() / "Videos",
            "music": Path.home() / "Music",
        }

    def create_folder(self, path: str) -> str:
        """Create a folder."""
        folder_path = self._clean_path(path)

        if folder_path is None:
            return "Please provide a folder path."

        folder_path.mkdir(parents=True, exist_ok=True)
        return f"Created folder at {folder_path}."

    def delete_folder(self, path: str) -> str:
        """Refuse direct folder deletion without a confirmation flow."""
        folder_path = self._clean_path(path)

        if folder_path is None:
            return "Please provide a folder path."

        if not folder_path.exists():
            return f"Folder not found: {folder_path}"

        return (
            f"Folder deletion requires confirmation for safety: {folder_path}. "
            "Use the manual delete option after reviewing the folder."
        )

    def rename_folder(self, old_path: str, new_path: str) -> str:
        """Rename a folder."""
        source = self._clean_path(old_path)
        destination = self._clean_path(new_path)

        if source is None or destination is None:
            return "Please provide both old and new folder paths."

        if not source.exists():
            return f"Folder not found: {source}"

        source.rename(destination)
        return f"Renamed folder to {destination}."

    def move_folder(self, source: str, destination: str) -> str:
        """Move a folder."""
        source_path = self._clean_path(source)
        destination_path = self._clean_path(destination)

        if source_path is None or destination_path is None:
            return "Please provide source and destination folders."

        if not source_path.exists():
            return f"Folder not found: {source_path}"

        shutil.move(str(source_path), str(destination_path))
        return f"Moved folder to {destination_path}."

    def copy_folder(self, source: str, destination: str) -> str:
        """Copy a folder."""
        source_path = self._clean_path(source)
        destination_path = self._clean_path(destination)

        if source_path is None or destination_path is None:
            return "Please provide source and destination folders."

        if not source_path.exists():
            return f"Folder not found: {source_path}"

        shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
        return f"Copied folder to {destination_path}."

    def create_file(self, path: str) -> str:
        """Create a file."""
        file_path = self._clean_path(path)

        if file_path is None:
            return "Please provide a file path."

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch(exist_ok=True)
        return f"Created file at {file_path}."

    def delete_file(self, path: str) -> str:
        """Refuse direct file deletion without a confirmation flow."""
        file_path = self._clean_path(path)

        if file_path is None:
            return "Please provide a file path."

        if not file_path.exists():
            return f"File not found: {file_path}"

        return (
            f"File deletion requires confirmation for safety: {file_path}. "
            "Use the manual delete option after reviewing the file."
        )

    def rename_file(self, old_path: str, new_path: str) -> str:
        """Rename a file."""
        source = self._clean_path(old_path)
        destination = self._clean_path(new_path)

        if source is None or destination is None:
            return "Please provide both old and new file paths."

        if not source.exists():
            return f"File not found: {source}"

        source.rename(destination)
        return f"Renamed file to {destination}."

    def move_file(self, source: str, destination: str) -> str:
        """Move a file."""
        source_path = self._clean_path(source)
        destination_path = self._clean_path(destination)

        if source_path is None or destination_path is None:
            return "Please provide source and destination files."

        if not source_path.exists():
            return f"File not found: {source_path}"

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        return f"Moved file to {destination_path}."

    def copy_file(self, source: str, destination: str) -> str:
        """Copy a file."""
        source_path = self._clean_path(source)
        destination_path = self._clean_path(destination)

        if source_path is None or destination_path is None:
            return "Please provide source and destination files."

        if not source_path.exists():
            return f"File not found: {source_path}"

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        return f"Copied file to {destination_path}."

    def open_folder(self, folder: str) -> str:
        """Open a known Windows user folder."""
        lowered = folder.lower().strip()

        for name, target in self.known_folders.items():
            if name in lowered:
                subprocess.Popen(["explorer.exe", str(target)])
                return f"Opened {name}."

        custom_path = self._clean_path(folder)
        if custom_path and custom_path.exists() and custom_path.is_dir():
            subprocess.Popen(["explorer.exe", str(custom_path)])
            return f"Opened {custom_path}."

        return f"I do not recognize the folder: {folder}."

    def search_files(self, query: str, max_results: int = 10) -> str:
        """Search common user folders for matching files."""
        clean_query = query.strip().lower()

        if not clean_query:
            return "Please provide a file name to search."

        matches: list[str] = []
        search_roots = [
            self.known_folders["desktop"],
            self.known_folders["documents"],
            self.known_folders["downloads"],
        ]

        for root in search_roots:
            if not root.exists():
                continue

            for path in root.rglob("*"):
                if clean_query in path.name.lower():
                    matches.append(str(path))

                    if len(matches) >= max_results:
                        break

            if len(matches) >= max_results:
                break

        if not matches:
            return f"No files found for {query}."

        return "\n".join(matches)

    def _clean_path(self, path: str) -> Path | None:
        """Normalize a path string."""
        clean_path = path.strip().strip('"').strip("'")

        if not clean_path:
            return None

        expanded = os.path.expandvars(os.path.expanduser(clean_path))
        return Path(expanded)