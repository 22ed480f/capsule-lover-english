"""Build the Windows installer."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path


def main():
    if os.name != "nt":
        raise SystemExit("Run this build with Windows Python (native Windows or Wine).")
    root = Path(__file__).resolve().parent
    os.chdir(root)
    notices = root / "build" / "THIRD-PARTY-NOTICES.txt"
    notices.parent.mkdir(exist_ok=True)
    sections = [
        "Capsule Lover English Patch: bundled third-party software\n"
        "This executable includes CPython, Tcl/Tk, PyInstaller, UnityPy, and their dependencies.\n"
        "The game itself and its assets belong to their respective owners.\n",
    ]
    for name in ("unitypy", "lz4", "brotli", "fsspec", "attrs", "tpk-ar", "pillow", "pyinstaller", "altgraph", "packaging", "pefile", "pywin32-ctypes", "setuptools"):
        distribution = importlib.metadata.distribution(name)
        sections.append(f"\n{name} {distribution.version}\n")
        for file in distribution.files or []:
            if file.name.lower().startswith(("license", "copying")):
                sections.append(distribution.locate_file(file).read_text(encoding="utf-8", errors="replace"))
    for file in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "tcl" / "tcl8.6" / "license.terms",
                 Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms"):
        if file.is_file():
            sections.append(f"\n{file.name}\n{file.read_text(encoding='utf-8', errors='replace')}")
    notices.write_text("\n".join(sections), encoding="utf-8")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "CapsuleLover-English", "--noupx",
        "--add-data", f"english.json{os.pathsep}.",
        "--add-data", f"{notices}{os.pathsep}.",
        "--collect-data", "UnityPy",
        # Script-only patching never uses UnityPy's optional audio/image exporters.
        "--exclude-module", "UnityPy.export", "--exclude-module", "fmod_toolkit",
        "--exclude-module", "pyfmodex",
        "--exclude-module", "etcpak", "--exclude-module", "astc_encoder",
        "--exclude-module", "texture2ddecoder", "--exclude-module", "numpy",
        # The optional C++ accelerator is unnecessary for raw script objects.
        # Its Python fallback avoids requiring an extra MSVC runtime on the PC.
        "--exclude-module", "UnityPy.UnityPyBoost",
        "gui.py",
    ], check=True)
    print(root / "dist" / "CapsuleLover-English.exe")


if __name__ == "__main__":
    main()
