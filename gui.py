"""One-window English installer; also exposes explicit CLI actions for testing."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import installer
import patch


def launch_game():
    uri = f"steam://run/{patch.APP_ID}"
    if os.name == "nt":
        os.startfile(uri)
    else:
        subprocess.Popen(["xdg-open", uri], start_new_session=True)


def relaunch_elevated(game: Path) -> bool:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                             ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
    shell_execute.restype = ctypes.c_void_p
    code = shell_execute(None, "runas", sys.executable,
                         subprocess.list2cmdline(["--game", str(game)]), None, 1)
    return bool(code and code > 32)


def run_window(initial_game: Path | None = None, smoke_test: bool = False) -> dict:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    root.title("Capsule Lover — English Patch")
    root.geometry("700x470")
    root.minsize(640, 470)
    root.configure(bg="#f7f8fb")
    data = patch.load_data()
    messages = queue.Queue()
    state = {"busy": False, "game": None, "permission": False}
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#f7f8fb")
    style.configure("TLabel", background="#f7f8fb", foreground="#17243b", font=("Segoe UI", 10))
    style.configure("TButton", font=("Segoe UI", 10), padding=(14, 9))
    style.configure("Accent.TButton", background="#245eea", foreground="white", borderwidth=0)
    style.map("Accent.TButton", background=[("disabled", "#9aa9c7"), ("active", "#174ac8")])
    style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
    style.configure("Small.TLabel", foreground="#596579", font=("Segoe UI", 9))
    outer = ttk.Frame(root, padding=26)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="Capsule Lover", style="Title.TLabel").pack(anchor="w")
    ttk.Label(outer, text=f"English patch · {patch.VERSION} · Steam build {data['game_build']}", style="Small.TLabel").pack(anchor="w", pady=(2, 22))
    ttk.Label(outer, text="Game location").pack(anchor="w")
    row = ttk.Frame(outer)
    row.pack(fill="x", pady=(6, 18))
    selected = tk.StringVar(value=str(initial_game) if initial_game else "")
    location = ttk.Combobox(row, textvariable=selected, state="readonly", font=("Segoe UI", 9))
    location.pack(side="left", fill="x", expand=True, ipady=5)
    status_text = tk.StringVar(value="Looking for your Steam installation…")
    status_label = ttk.Label(outer, textvariable=status_text, wraplength=620, justify="left", font=("Segoe UI", 11))
    status_label.pack(anchor="w", fill="x")
    progress = ttk.Progressbar(outer, mode="indeterminate")
    progress.pack(fill="x", pady=(18, 16))
    buttons = ttk.Frame(outer)
    buttons.pack(fill="x")

    def work(action, message):
        if state["busy"]:
            return
        state["busy"] = True
        state["permission"] = False
        status_text.set(message)
        for button in (install_button, restore_button, play_button, browse_button):
            button.configure(state="disabled")
        location.configure(state="disabled")
        progress.start(12)

        def execute():
            try:
                messages.put(("ok", action()))
            except Exception as error:
                messages.put(("error", error))
        threading.Thread(target=execute, daemon=True).start()

    def inspect(game):
        result = installer.status(game, data)
        result["kind"] = "status"
        return result

    def refresh():
        if selected.get():
            work(lambda: inspect(Path(selected.get())), "Checking your game version…")

    def choose_game():
        filename = filedialog.askopenfilename(
            parent=root, title="Select CapsuleLover.exe in your Steam game folder",
            filetypes=[("Capsule Lover", "CapsuleLover.exe"), ("Programs", "*.exe")],
        )
        if filename:
            selected.set(str(Path(filename).parent))
            refresh()

    def apply():
        if state["permission"]:
            if relaunch_elevated(Path(selected.get())):
                root.destroy()
            else:
                messagebox.showerror("Permission needed", "Windows permission was not granted. Your game file has not been changed.", parent=root)
            return
        if not selected.get():
            choose_game()
            return
        game = Path(selected.get())

        def action():
            installer.install(game, data)
            return inspect(game)
        work(action, "Building and checking the English patch. Please keep the game closed…")

    def undo():
        if not messagebox.askyesno("Restore original", "Restore the original Chinese script file? Your saves will be kept.", parent=root):
            return
        game = Path(selected.get())

        def action():
            installer.restore(game, data)
            return inspect(game)
        work(action, "Restoring the verified original file…")

    def play():
        try:
            launch_game()
        except OSError as error:
            messagebox.showerror("Open Steam", f"Please start Capsule Lover through Steam.\n\n{error}", parent=root)

    install_button = ttk.Button(buttons, text="Install English", command=apply, style="Accent.TButton")
    install_button.pack(side="left")
    play_button = ttk.Button(buttons, text="Play", command=play, state="disabled")
    play_button.pack(side="left", padx=10)
    restore_button = ttk.Button(buttons, text="Restore Original", command=undo, state="disabled")
    restore_button.pack(side="right")
    browse_button = ttk.Button(row, text="Choose game…", command=choose_game)
    browse_button.pack(side="right", padx=(10, 0))
    ttk.Label(outer, text="Unofficial AI-translated beta. Keep Simplified Chinese selected in the game.",
              style="Small.TLabel", wraplength=620).pack(anchor="w", pady=(20, 0))
    location.bind("<<ComboboxSelected>>", lambda event: refresh())

    def found():
        games = installer.detect_games()
        return {"kind": "found", "games": [str(game) for game in games]}

    def poll():
        try:
            result, value = messages.get_nowait()
        except queue.Empty:
            root.after(75, poll)
            return
        state["busy"] = False
        progress.stop()
        browse_button.configure(state="normal")
        location.configure(state="readonly")
        install_button.configure(text="Install English", state="normal")
        if result == "error":
            if isinstance(value, PermissionError) and os.name == "nt" and getattr(sys, "frozen", False):
                state["permission"] = True
                status_text.set("Windows needs permission to write to this game folder. Click Grant Permission, then install again.")
                install_button.configure(text="Grant Permission")
            else:
                status_text.set(str(value))
                install_button.configure(text="Retry")
        elif value["kind"] == "found":
            location.configure(values=value["games"])
            if len(value["games"]) == 1:
                selected.set(value["games"][0])
                refresh()
            elif value["games"]:
                status_text.set("More than one installation was found. Choose the one you play from the list.")
                install_button.configure(state="disabled")
            else:
                status_text.set("Choose CapsuleLover.exe from your Steam game folder to get started.")
        else:
            selected.set(value["game"])
            if value["state"] == "original":
                status_text.set("Your game is compatible. Click Install English to begin.")
                play_button.configure(state="normal")
            elif value["state"] == "installed":
                status_text.set("English is installed. You're ready to play through Steam.")
                install_button.configure(text="English Installed", state="disabled")
                play_button.configure(state="normal")
                restore_button.configure(state="normal" if value["can_restore"] else "disabled")
                if not value["can_restore"]:
                    status_text.set("English is installed. To restore Chinese, use Steam's Verify integrity of game files; no installer backup was found.")
            else:
                status_text.set(f"This game version needs a different patch. This release supports Steam build {data['game_build']}. Check the download page for an updated release.")
                install_button.configure(state="disabled")
        root.after(75, poll)

    def close():
        if state["busy"]:
            messagebox.showinfo("Please wait", "Let the current operation finish before closing the installer.", parent=root)
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    if smoke_test:
        root.update()
        result = {"gui_created": True, "width": root.winfo_width(), "height": root.winfo_height(),
                  "requested_height": root.winfo_reqheight()}
        root.destroy()
        return result
    root.after(75, poll)
    root.after(100, refresh if initial_game else lambda: work(found, "Looking for your Steam installation…"))
    root.mainloop()
    return {"closed": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path)
    parser.add_argument("--action", choices=("status", "build", "install", "restore", "detect", "self-test"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        data = patch.load_data()
        if args.action == "self-test":
            import UnityPy
            from UnityPy.helpers.Tpk import get_typetree
            get_typetree()
            result = {"version": patch.VERSION, "translation_fields": data["translation_fields"],
                      "unitypy_version": UnityPy.__version__, "patch_backend_loaded": True,
                      "data_sha256": patch.digest(patch.DATA_FILE.read_bytes()), **run_window(smoke_test=True)}
        elif args.action == "detect":
            result = {"games": [str(path) for path in installer.detect_games()]}
        elif args.action:
            if args.game is None:
                raise patch.PatchError("--game is required for this action.")
            if args.action == "build":
                if args.output is None:
                    raise patch.PatchError("--output is required when building.")
                target = patch.build(args.game, args.output, data)
                result = {"output": str(target), "sha256": patch.digest(target.read_bytes())}
            elif args.action == "status":
                result = installer.status(args.game, data)
            else:
                result = {"message": (installer.install if args.action == "install" else installer.restore)(args.game, data)}
        else:
            run_window(args.game)
            return 0
        code = 0
    except Exception as error:
        result, code = {"error": str(error)}, 1
        if not args.action:
            import tkinter.messagebox
            tkinter.messagebox.showerror("Capsule Lover English Patch", str(error))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if sys.stdout is not None:
        print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
