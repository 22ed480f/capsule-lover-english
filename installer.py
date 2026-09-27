"""Steam detection and reversible installation, shared by GUI and test tools."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import patch


def parse_vdf(text: str) -> dict:
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]', text)
    cursor = 0

    def read_map(nested=False):
        nonlocal cursor
        result = {}
        while cursor < len(tokens):
            key = tokens[cursor]
            cursor += 1
            if key == "}":
                if not nested:
                    raise ValueError("Unexpected closing brace")
                return result
            if not key.startswith('"') or cursor == len(tokens):
                raise ValueError("Invalid Steam configuration")
            key = re.sub(r'\\([\\"])', r'\1', key[1:-1])
            value = tokens[cursor]
            cursor += 1
            if value == "{":
                result[key] = read_map(True)
            elif value.startswith('"'):
                result[key] = re.sub(r'\\([\\"])', r'\1', value[1:-1])
            else:
                raise ValueError("Invalid Steam value")
        if nested:
            raise ValueError("Unclosed Steam configuration")
        return result

    return read_map()


def steam_roots() -> list[Path]:
    paths = []
    if os.name == "nt":
        import winreg

        for hive, name, value in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, name) as key:
                    paths.append(Path(winreg.QueryValueEx(key, value)[0]))
            except OSError:
                pass
        for name in ("ProgramFiles(x86)", "ProgramFiles"):
            if os.environ.get(name):
                paths.append(Path(os.environ[name]) / "Steam")
    else:
        paths.extend(Path.home() / name for name in (
            ".local/share/Steam", ".steam/steam",
            ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        ))
    if os.environ.get("STEAM_COMPAT_CLIENT_INSTALL_PATH"):
        paths.append(Path(os.environ["STEAM_COMPAT_CLIENT_INSTALL_PATH"]))
    return list(dict.fromkeys(path.resolve() for path in paths))


def detect_games(roots: list[Path] | None = None) -> list[Path]:
    libraries = set(steam_roots() if roots is None else roots)
    for root in list(libraries):
        config = root / "steamapps/libraryfolders.vdf"
        try:
            entries = parse_vdf(config.read_text(encoding="utf-8-sig"))["libraryfolders"]
            for index, entry in entries.items():
                if index.isdecimal():
                    value = entry.get("path") if isinstance(entry, dict) else entry
                    if value:
                        libraries.add(Path(value))
        except (OSError, ValueError, KeyError, AttributeError):
            continue
    found = set()
    for library in libraries:
        manifest = library / f"steamapps/appmanifest_{patch.APP_ID}.acf"
        try:
            state = parse_vdf(manifest.read_text(encoding="utf-8-sig"))["AppState"]
            directory = state["installdir"]
            if state["appid"] != str(patch.APP_ID) or "/" in directory or "\\" in directory or directory in (".", ".."):
                continue
            root = patch.game_root(library / "steamapps/common" / directory)
            if (root / "CapsuleLover.exe").is_file():
                found.add(root)
        except (OSError, ValueError, KeyError, patch.PatchError):
            continue
    return sorted(found, key=str)


def ensure_game_closed() -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq CapsuleLover.exe", "/FO", "CSV", "/NH"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15,
        )
        if result.returncode:
            raise patch.PatchError("Could not check whether the game is running. Close the game and retry.")
        running = any(
            row and row[0].casefold() == "capsulelover.exe"
            for row in csv.reader(io.StringIO(result.stdout.decode(errors="replace")))
        )
    else:
        running = False
        for proc in Path("/proc").glob("[0-9]*/comm"):
            try:
                running |= proc.read_text().strip().casefold().startswith("capsulelover")
            except (OSError, ProcessLookupError):
                continue
    if running:
        raise patch.PatchError("Close Capsule Lover, then click Retry.")


def backup_path(game: Path, data: dict) -> Path:
    return game / ".capsule-english" / f"scripts-{data['original_sha256']}.backup"


def status(game: Path, data: dict) -> dict:
    game = patch.game_root(game)
    current = patch.digest((game / patch.BUNDLE_PATH).read_bytes())
    state = "original" if current == data["original_sha256"] else "installed" if current == data["patched_sha256"] else "unsupported"
    backup = backup_path(game, data)
    valid_backup = backup.is_file() and patch.digest(backup.read_bytes()) == data["original_sha256"]
    return {"state": state, "can_restore": state == "installed" and valid_backup, "game": str(game)}


@contextlib.contextmanager
def installation_lock(game: Path):
    folder = game / ".capsule-english"
    folder.mkdir(exist_ok=True)
    with (folder / "installer.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise patch.PatchError("Another patch installer is open. Close it and try again.") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def atomic_replace(target: Path, content: bytes, expected_current: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".english-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(target, temporary)
        if patch.digest(Path(temporary).read_bytes()) != patch.digest(content):
            raise patch.PatchError("Could not verify the temporary file. Your game file is unchanged.")
        ensure_game_closed()
        if patch.digest(target.read_bytes()) != expected_current:
            raise patch.PatchError("The game files changed during installation. Wait for Steam to finish updating, then retry.")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(game: Path, data: dict) -> str:
    game = patch.game_root(game)
    ensure_game_closed()
    with installation_lock(game):
        target = game / patch.BUNDLE_PATH
        original = target.read_bytes()
        original_hash = patch.digest(original)
        if original_hash == data["patched_sha256"]:
            return "English is already installed."
        # Build and fully verify before creating a backup or touching the game file.
        result = patch.build_bytes(original, data)
        backup = backup_path(game, data)
        if backup.exists():
            if patch.digest(backup.read_bytes()) != data["original_sha256"]:
                raise patch.PatchError("The original-file backup is damaged. Installation stopped; your game file is unchanged.")
        else:
            try:
                with backup.open("xb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError:
                backup.unlink(missing_ok=True)
                raise
        if patch.digest(backup.read_bytes()) != data["original_sha256"]:
            raise patch.PatchError("Backup verification failed. Your game file is unchanged.")
        atomic_replace(target, result, original_hash)
    return "English installed. Keep Simplified Chinese selected in the game."


def restore(game: Path, data: dict) -> str:
    game = patch.game_root(game)
    ensure_game_closed()
    with installation_lock(game):
        target = game / patch.BUNDLE_PATH
        current_hash = patch.digest(target.read_bytes())
        if current_hash == data["original_sha256"]:
            return "The original game file is already restored."
        if current_hash != data["patched_sha256"]:
            raise patch.PatchError("The game has changed since this patch. Use Steam's Verify integrity of game files to restore its current version.")
        backup = backup_path(game, data)
        if not backup.is_file() or patch.digest(backup.read_bytes()) != data["original_sha256"]:
            raise patch.PatchError("A valid original backup is unavailable. Use Steam's Verify integrity of game files.")
        atomic_replace(target, backup.read_bytes(), current_hash)
    return "Original game file restored."


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "install", "restore", "detect"))
    parser.add_argument("game", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "detect":
            print(json.dumps([str(path) for path in detect_games()]))
            return
        if args.game is None:
            parser.error("the game path is required")
        data = patch.load_data()
        if args.action == "status":
            print(json.dumps(status(args.game, data)))
        else:
            print((install if args.action == "install" else restore)(args.game, data))
    except (patch.PatchError, OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
