"""Create explicit, clean release archives without invoking Git or uploading."""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_FILES = [
    "patch.py", "patch.py.lock", "installer.py", "gui.py", "pyproject.toml", "uv.lock",
    "README.md", "THIRD-PARTY.md", "english.json",
    "installer-example.png", "english-example.png",
    ".gitignore", ".github/workflows/build.yml", "build_windows.py", "package_release.py",
]
PYTHON_README = """# Capsule Lover — minimal Python patcher

Unofficial AI-translated beta 0.1.0-beta.1. Supports Steam build 25049583.
Requires an installed copy of Capsule Lover.

Install uv: https://docs.astral.sh/uv/getting-started/installation/

Then run from this folder (replace the game path):

    uv run --script patch.py "D:\\SteamLibrary\\steamapps\\common\\Capsule Lover" --output ./patched

On Linux/Steam Deck, supply the corresponding Steam game folder.
This writes a verified scripts.nvldata under patched/, retaining the game's
relative folder layout. It does not modify the game. Add --objects to also
export the 30 modified serialized TextAssets for development/inspection.

To install manually, close the game, back up its original scripts.nvldata,
then copy the generated file into the matching game folder. Keep Simplified
Chinese selected in the game. Restore the backup only to the same game version;
Steam file verification restores the currently installed official version.

The first run downloads dependencies. The executable version includes them.
The translation data contains English strings and source-validation hashes.
This package contains no original game bundle and no API keys or model calls.
"""
WINDOWS_README = """CAPSULE LOVER — UNOFFICIAL ENGLISH PATCH
Version 0.1.0-beta.1 / Steam build 25049583

1. Open CapsuleLover-English.exe.
2. Click Install English. Close the game if asked.
3. Click Play to launch through Steam.

Keep Simplified Chinese selected in the game.
If the game is not found, click Choose game and select CapsuleLover.exe.
To undo this install, open the installer and click Restore Original.

The installer checks the game version, builds and verifies the translated
script file, and backs up the original in .capsule-english inside the game
folder. It preserves saves, voices, images and all other bundles.
It works offline and requires no Python installation.

After a game update, get the matching patch. The installer refuses unknown
game versions. Steam > Properties > Installed Files > Verify integrity of
game files restores the official files for the current version.

This is an unsigned, AI-translated beta. Expect translation mistakes.
See THIRD-PARTY-NOTICES.txt for bundled software licenses.
"""


def archive(path: Path, files: dict[str, bytes]):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for name, content in sorted(files.items()):
            if name.endswith((".nvldata", ".backup", ".log")) or ".git/" in name or name == ".env":
                raise ValueError(f"Private/build file in release: {name}")
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            stream.writestr(info, content)


def main():
    output = ROOT / "dist/release"
    output.mkdir(parents=True, exist_ok=True)
    source = {name: (ROOT / name).read_bytes() for name in SOURCE_FILES}
    private_markers = [str(Path.home()).encode().lower(), ("sk-" + "or-v1-").encode()]
    for name, content in source.items():
        if any(len(token) > 3 and token in content.lower() for token in private_markers):
            raise ValueError(f"Personal path or credential marker in public source: {name}")
    archive(output / "CapsuleLover-English-Source.zip", source)
    minimal = {name: source[name] for name in ("patch.py", "patch.py.lock", "english.json", "THIRD-PARTY.md")}
    minimal["README.md"] = PYTHON_README.encode("utf-8")
    archive(output / "CapsuleLover-English-Python.zip", minimal)
    exe = ROOT / "dist/CapsuleLover-English.exe"
    if exe.is_file():
        notices = (ROOT / "build/THIRD-PARTY-NOTICES.txt").read_bytes()
        shutil.copyfile(exe, output / exe.name)
        (output / "THIRD-PARTY-NOTICES.txt").write_bytes(notices)
        archive(output / "CapsuleLover-English-Windows.zip", {
            exe.name: exe.read_bytes(), "INSTALL.txt": WINDOWS_README.encode("utf-8"),
            "THIRD-PARTY-NOTICES.txt": notices,
        })
    checksums = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS.txt"]
    (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    for path in sorted(output.iterdir()):
        print(f"{path.name}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
