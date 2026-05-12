#!/usr/bin/env python3
"""
Steam recent games context menu for Waybar.
Right-click on the Steam button → picks menu launcher (wofi/rofi/fuzzel/bemenu)
and shows recently played games. Click to launch.

Usage: python3 steam-menu.py [--limit N]
"""

import os
import re
import subprocess
import sys
import argparse

STEAM_DIR  = os.path.expanduser("~/.local/share/Steam")
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CSS_FILE   = os.path.join(SCRIPT_DIR, "steam-menu.css")

# ─── Steam data ──────────────────────────────────────────────────────────────

def find_steam_libraries() -> list[str]:
    """Return list of steamapps directories (main + extra libraries)."""
    libs = [os.path.join(STEAM_DIR, "steamapps")]
    vdf = os.path.join(STEAM_DIR, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        with open(vdf, errors="ignore") as f:
            content = f.read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', content):
            extra = os.path.join(m.group(1), "steamapps")
            if extra not in libs:
                libs.append(extra)
    return libs


def get_game_name(appid: str, libs: list[str]) -> str | None:
    """Read game name from appmanifest_<appid>.acf. Returns None if not installed."""
    for lib in libs:
        manifest = os.path.join(lib, f"appmanifest_{appid}.acf")
        if os.path.exists(manifest):
            with open(manifest, errors="ignore") as f:
                m = re.search(r'"name"\s+"([^"]+)"', f.read())
                if m:
                    return m.group(1)
    return None


def get_recent_games(limit: int = 10) -> list[tuple[str, str]]:
    """
    Parse localconfig.vdf for all app LastPlayed timestamps,
    sort descending, return [(appid, name), ...] for installed games only.
    """
    userdata = os.path.join(STEAM_DIR, "userdata")
    if not os.path.exists(userdata):
        return []

    apps: dict[str, int] = {}

    for uid in os.listdir(userdata):
        cfg = os.path.join(userdata, uid, "config", "localconfig.vdf")
        if not os.path.exists(cfg):
            continue
        with open(cfg, errors="ignore") as f:
            content = f.read()

        # Match any numeric ID block containing a LastPlayed entry
        # Works for both "Apps" section and "RecentGames" section
        for m in re.finditer(
            r'"(\d{4,})"[^{]*\{[^}]*?"LastPlayed"\s+"(\d+)"',
            content,
            re.DOTALL,
        ):
            appid, ts = m.group(1), int(m.group(2))
            if ts > 0 and (appid not in apps or apps[appid] < ts):
                apps[appid] = ts

    if not apps:
        return []

    libs = find_steam_libraries()
    results: list[tuple[str, str]] = []

    for appid, _ in sorted(apps.items(), key=lambda x: -x[1]):
        name = get_game_name(appid, libs)
        if name:
            results.append((appid, name))
            if len(results) >= limit:
                break

    return results


# ─── Menu launchers ───────────────────────────────────────────────────────────

def _wofi_cmd() -> list[str]:
    cmd = ["wofi", "--dmenu", "--prompt=🎮 Recent Games  "]
    if os.path.exists(CSS_FILE):
        cmd += ["--style", CSS_FILE]
    return cmd

LAUNCHERS = [
    _wofi_cmd,                                           # callable → evaluated at runtime
    lambda: ["rofi",   "-dmenu", "-p", "Recent Games"],
    lambda: ["fuzzel", "--dmenu", "--prompt=Recent Games> "],
    lambda: ["bemenu", "-p", "Recent Games"],
    lambda: ["dmenu"],
]


def run_menu(entries: str) -> str | None:
    """Try each launcher in order, return the selected line or None."""
    for launcher in LAUNCHERS:
        cmd = launcher()
        try:
            result = subprocess.run(
                cmd, input=entries, capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
            return None          # user cancelled
        except FileNotFoundError:
            continue
    return None


# ─── Actions ─────────────────────────────────────────────────────────────────

def launch_game(appid: str) -> None:
    subprocess.Popen(
        ["steam", f"steam://rungameid/{appid}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def notify(title: str, body: str) -> None:
    subprocess.run(
        ["notify-send", "-i", "steam", "-a", "Steam", title, body],
        check=False,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Steam recent games menu")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max number of recent games to show (default: 10)")
    parser.add_argument("--debug", action="store_true",
                        help="Print debug info and exit without showing menu")
    args = parser.parse_args()

    if args.debug:
        print(f"Steam dir: {STEAM_DIR}  (exists: {os.path.exists(STEAM_DIR)})")
        userdata = os.path.join(STEAM_DIR, "userdata")
        print(f"Userdata exists: {os.path.exists(userdata)}")
        if os.path.exists(userdata):
            print(f"User IDs: {os.listdir(userdata)}")
        print(f"Libraries: {find_steam_libraries()}")
        games_dbg = get_recent_games(limit=args.limit)
        print(f"\nFound {len(games_dbg)} recent installed games:")
        for appid, name in games_dbg:
            print(f"  [{appid}] {name}")
        print("\nLaunchers:")
        for cmd in LAUNCHERS:
            available = subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0
            print(f"  {cmd[0]}: {'OK' if available else 'NOT FOUND'}")
        return

    games = get_recent_games(limit=args.limit)

    if not games:
        notify("Steam", "No recently played games found.\nMake sure Steam has run at least once.")
        sys.exit(1)

    # Build menu text: one game per line
    entries = "\n".join(name for _, name in games)
    name_to_id = {name: appid for appid, name in games}

    selected = run_menu(entries)

    if selected and selected in name_to_id:
        launch_game(name_to_id[selected])


if __name__ == "__main__":
    main()
