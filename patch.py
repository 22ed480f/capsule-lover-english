#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["UnityPy==1.25.3", "lz4==4.4.5"]
# ///
"""Build the English bundle from the player's game and editable translation data.

uv run patch.py "/path/to/Capsule Lover" --output ./patched
This entry point never installs into the game. installer.py adds installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

VERSION = "0.1.0-beta.1"
APP_ID = 3559510
DATA_FILE = Path(__file__).resolve().parent / "english.json"
BUNDLE_PATH = Path("CapsuleLover_Data/StreamingAssets/StandaloneWindows/CapsuleLover/scripts.nvldata")
KEY = bytes.fromhex("8b05ead7d77cb68eef4349a1")
HEADER = bytes.fromhex("556e69747946530000000008352e782e7800363030302e302e34326631000000")
CONTROL = re.compile(b"([\x00\xfe\xff])")


class PatchError(Exception):
    """An actionable error suitable for the installer and command line."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_data(path: Path = DATA_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["format_version"] != 1 or data["app_id"] != APP_ID:
        raise PatchError("This translation data belongs to a different patch.")
    if data["bundle_path"] != BUNDLE_PATH.as_posix():
        raise PatchError("Unexpected bundle path in translation data.")
    return data


def game_root(path: Path) -> Path:
    root = path.expanduser().resolve()
    if root.name.casefold() == "capsulelover.exe":
        root = root.parent
    if not (root / BUNDLE_PATH).is_file():
        raise PatchError("Game not found. Select CapsuleLover.exe or its containing folder.")
    return root


def decode(data: bytes):
    import UnityPy

    if len(data) < 32:
        raise PatchError("The game script file is incomplete.")
    return UnityPy.load(HEADER + bytes(value ^ KEY[i % len(KEY)] for i, value in enumerate(data[32:], 32)))


def payload(raw: bytes) -> tuple[str, bytes, int]:
    length = struct.unpack_from("<I", raw)[0]
    name = raw[4:4 + length].decode("utf-8")
    size_at = (4 + length + 3) & ~3
    size = struct.unpack_from("<I", raw, size_at)[0]
    start = size_at + 4
    script = raw[start:start + size]
    if len(script) != size or any(raw[start + size:]):
        raise PatchError(f"Unexpected script layout: {name}")
    return name, script, start


def require_source(part: bytes, row: dict, label: str) -> None:
    if digest(part) != row["original_sha256"]:
        raise PatchError(f"Source field does not match: {label}:{row['segment']}")


def translated_object(raw: bytes, asset: dict) -> bytes:
    if digest(raw) != asset["original_sha256"]:
        raise PatchError(f"Source object does not match: {asset['name']}")
    name, script, start = payload(raw)
    if name != asset["name"]:
        raise PatchError("Source object name does not match.")
    parts = CONTROL.split(script)
    edited = set()
    for row in asset["fields"] + asset["layout"]:
        index = row["segment"]
        if not isinstance(index, int) or not 0 <= index < len(parts) or index % 2 or index in edited:
            raise PatchError(f"Invalid or duplicate field in {name}.")
        edited.add(index)
        original = parts[index]
        require_source(original, row, name)
        if "english" in row:
            prefix = bytes.fromhex(row["prefix"])
            encoded = row["english"].encode("utf-8")
            if not encoded or len(encoded) > 252 or any(byte in (0, 254, 255) for byte in encoded):
                raise PatchError(f"Translation does not fit: {name}:{index}")
            boundary = len(prefix)
            if (not original.startswith(prefix) or boundary >= len(original)
                    or original[boundary] != len(original) - boundary):
                raise PatchError(f"Invalid field metadata: {name}:{index}")
            parts[index] = prefix + bytes([len(encoded) + 1]) + encoded
        elif row["kind"] == "textsize":
            if original != bytes([row["source"]]):
                raise PatchError("Font size source does not match.")
            parts[index] = bytes([row["value"]])
        elif row["kind"] == "DefaultFontSize":
            before = f"DefaultFontSize={row['source']};".encode()
            after = f"DefaultFontSize={row['value']};".encode()
            if original.count(before) != 1:
                raise PatchError("Default font size source does not match.")
            parts[index] = original.replace(before, after)
        elif row["kind"] == "linespace":
            before, after = row["source"].encode(), row["value"].encode()
            if original != bytes([len(before) + 1]) + before:
                raise PatchError("Line spacing source does not match.")
            parts[index] = bytes([len(after) + 1]) + after
        else:
            raise PatchError("Unknown layout edit.")
    script = b"".join(parts)
    result = raw[:start - 4] + struct.pack("<I", len(script)) + script
    result += bytes(-len(result) % 4)
    if digest(result) != asset["patched_sha256"]:
        raise PatchError(f"Patched object verification failed: {name}")
    return result


def build_bytes(original: bytes, data: dict) -> bytes:
    original_hash = digest(original)
    if original_hash == data["patched_sha256"]:
        return original
    if original_hash != data["original_sha256"]:
        raise PatchError(
            f"This patch supports Steam build {data['game_build']}. Your script file is a different "
            "version or has another modification. Use the matching English patch."
        )
    env = decode(original)
    objects = {obj.path_id: obj for obj in env.objects}
    expected = {pid: digest(obj.get_raw_data()) for pid, obj in objects.items()}
    seen = set()
    for asset in data["assets"]:
        pid = asset["path_id"]
        if pid in seen or pid not in objects or objects[pid].type.name != "TextAsset":
            raise PatchError("Unexpected or duplicate translated object.")
        seen.add(pid)
        result = translated_object(objects[pid].get_raw_data(), asset)
        objects[pid].set_raw_data(result)
        expected[pid] = asset["patched_sha256"]
    packed = env.file.save(packer="lz4")
    if not packed.startswith(HEADER):
        raise PatchError("Unexpected bundle format after patching.")
    output = original[:32] + bytes(value ^ KEY[i % len(KEY)] for i, value in enumerate(packed[32:], 32))
    readback = {obj.path_id: digest(obj.get_raw_data()) for obj in decode(output).objects}
    if readback != expected or digest(output) != data["patched_sha256"]:
        raise PatchError("Output verification failed. No game files were changed.")
    return output


def write_new(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == content:
            return
        raise PatchError(f"Output already exists: {path}. Choose an empty output folder.")
    with path.open("xb") as stream:
        stream.write(content)


def build(game: Path, output: Path, data: dict, export_objects: bool = False) -> Path:
    game = game_root(game)
    target = (output / BUNDLE_PATH).resolve()
    if target == (game / BUNDLE_PATH).resolve():
        raise PatchError("Choose a separate output folder. This command does not install into the game.")
    result = build_bytes((game / BUNDLE_PATH).read_bytes(), data)
    write_new(target, result)
    if export_objects:
        wanted = {asset["path_id"] for asset in data["assets"]}
        for obj in decode(result).objects:
            if obj.path_id in wanted:
                write_new(output / "objects" / f"{obj.path_id}.bin", obj.get_raw_data())
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="Game folder or CapsuleLover.exe")
    parser.add_argument("--output", type=Path, required=True, help="Separate output folder")
    parser.add_argument("--data", type=Path, default=DATA_FILE)
    parser.add_argument("--objects", action="store_true", help="Also export modified serialized TextAssets")
    args = parser.parse_args(argv)
    try:
        target = build(args.game, args.output, load_data(args.data), args.objects)
    except (PatchError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"Built and verified: {target}\nSHA-256: {digest(target.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
