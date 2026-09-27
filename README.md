# Capsule Lover English Patch

An unofficial English translation for [Capsule Lover](https://store.steampowered.com/app/3559510/).

![Capsule Lover](https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3559510/82100aa61e55058d6fda71dc00f1a670efec5632/header.jpg?t=1781236275)

# Installation (Windows)

1. Download **CapsuleLover-English.exe** from [Releases](https://github.com/22ed480f/capsule-lover-english/releases).
2. Close the game, open the installer, and click **Install English**.
3. Click **Play**. Keep **Simplified Chinese** selected in the game.

If the game isn't found, click **Choose game…** and select `CapsuleLover.exe`. [Report a problem](https://github.com/22ed480f/capsule-lover-english/issues).

---

# Manual Patch

Prefer not to run the EXE? Use the Python script instead.

1. [Download the source ZIP](https://github.com/22ed480f/capsule-lover-english/archive/refs/heads/main.zip), extract it, and [install uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Open a terminal in the extracted folder and run this, replacing the game path:

   ```powershell
   uv run --script patch.py "D:\SteamLibrary\steamapps\common\Capsule Lover" --output ./patched
   ```

3. Close the game. Back up `CapsuleLover_Data/StreamingAssets/StandaloneWindows/CapsuleLover/scripts.nvldata` in your game folder.
4. Copy `CapsuleLover_Data` from the new `patched` folder into your game folder and replace the existing file. Keep **Simplified Chinese** selected.

# FAQ

**Is this AI-translated?** Yes. Expect mistakes.

**How do I remove it?** Click **Restore Original** in the installer, restore your manual backup, or verify the game's files in Steam.

**What if the game updates?** Wait for a compatible patch. The installer refuses unsupported versions. Don't restore an old backup over an updated game.
