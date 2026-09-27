# Third-party software

The Python builder uses [UnityPy](https://github.com/K0lb3/UnityPy), pinned to
1.25.3, and its dependencies. Dependency versions and artifact hashes are
recorded in the uv lockfiles.

The Windows executable also bundles CPython, Tcl/Tk and PyInstaller runtime
components. `build_windows.py` generates `THIRD-PARTY-NOTICES.txt` from
the installed dependencies and interpreter and embeds it in the executable.
The generated notice is also included in the Windows ZIP.

UnityPy's optional image/audio exporters and C++ accelerator are excluded from
the executable because this patch edits raw script objects only. No FMOD
binary, original game script bundle, font atlas, CG or voice recording is
distributed with these packages.

This is an unofficial fan patch. Capsule Lover and its original content belong
to their respective owners. No developer or publisher endorsement is claimed.
