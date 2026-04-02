#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

VERSION = "0.0.1"
GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/nikolayli/deck_cleaner/main/cleaner.py"
)
STEAM_ROOT = os.path.expanduser("~/.steam/steam")
STEAMAPPS = os.path.join(STEAM_ROOT, "steamapps")
LOGS_PATH = os.path.join(STEAM_ROOT, "logs")


def check_for_updates():
    try:
        with urllib.request.urlopen(GITHUB_RAW_URL, timeout=3) as response:
            content = response.read().decode()

            match = re.search(r'VERSION = "(.*?)"', content)

            if match:
                remote_version = match.group(1)

                if remote_version > VERSION:
                    ask = subprocess.run(
                        [
                            "zenity",
                            "--question",
                            "--title",
                            "The update is available",
                            "--text",
                            f"A new version of {remote_version} is available (you have {VERSION}). Update?",
                        ]
                    )

                    if ask.returncode == 0:
                        with open(__file__, "w") as f:
                            f.write(content)
                        subprocess.run(
                            [
                                "zenity",
                                "--info",
                                "--text",
                                "The script has been updated! Please rerun it.",
                            ]
                        )
                        sys.exit(0)
            else:
                print("Could not find version info in the remote file.")

    except Exception as e:
        print(f"Error checking for updates: {e}")


def get_library_folders():
    vdf_path = os.path.join(STEAMAPPS, "libraryfolders.vdf")
    paths = [STEAMAPPS]
    if os.path.exists(vdf_path):
        with open(vdf_path, "r") as f:
            found_paths = re.findall(r'"path"\s*"(.*?)"', f.read())
            for p in found_paths:
                full_p = os.path.join(p, "steamapps")
                if full_p not in paths and os.path.isdir(full_p):
                    paths.append(full_p)
    return paths


def get_steam_api_list():
    url = "https://steampowered.com"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            return {str(app["appid"]): app["name"] for app in data["applist"]["apps"]}
    except:
        return {}


def get_name_from_logs(appid):
    for log in ["controller_ui.txt", "content_log.txt"]:
        log_path = os.path.join(LOGS_PATH, log)
        if os.path.exists(log_path):
            with open(log_path, "r", errors="ignore") as f:
                for line in reversed(f.readlines()):
                    if appid in line:
                        match = re.search(r"AppID\s\d+,\s(.*)", line) or re.search(
                            r"AppId=(\d+)\s(.*)", line
                        )
                        if match:
                            return match.groups()[-1].strip()
    return "Unknown"


def get_folder_size(path):
    try:
        total = 0
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_folder_size(entry.path)
        return total // (1024 * 1024)
    except:
        return 0


def collect_data(target_type, library_paths, api_names):
    info_list = []
    target_dir = os.path.join(STEAMAPPS, target_type)
    if not os.path.exists(target_dir):
        return []

    for appid in os.listdir(target_dir):
        full_path = os.path.join(target_dir, appid)
        if not os.path.isdir(full_path) or not appid.isdigit():
            continue
        if "Proton" in appid:
            continue

        name = None
        for lib in library_paths:
            m_path = os.path.join(lib, f"appmanifest_{appid}.acf")
            if os.path.exists(m_path):
                with open(m_path, "r", errors="ignore") as f:
                    m = re.search(r'"name"\s*"(.*?)"', f.read())
                    if m:
                        name = m.group(1)
                        break

        info = "Local"
        if not name:
            name = api_names.get(appid)
            info = "Uninstalled?" if name else "Non-Steam"
        if not name:
            name = get_name_from_logs(appid)
        if "Proton" in (name or ""):
            continue

        size = get_folder_size(full_path)
        info_list.append(
            ["FALSE", str(size), appid, name or "Unknown", info, full_path]
        )

    return sorted(info_list, key=lambda x: int(x[1]), reverse=True)


def main(mode="shadercache"):
    check_for_updates()

    next_mode = "compatdata" if mode == "shadercache" else "shadercache"
    libs = get_library_folders()
    api_names = get_steam_api_list()
    data = collect_data(mode, libs, api_names)

    cmd = [
        "zenity",
        "--list",
        "--checklist",
        "--title",
        f"Cleanup {mode} (v{VERSION})",
        "--width=1100",
        "--height=720",
        "--print-column=6",
        "--separator=|",
        "--column=Choice",
        "--column=Size (MB)",
        "--column=ID",
        "--column=Name",
        "--column=Info",
        "--column=Path",
        "--extra-button",
        next_mode,
    ]
    for row in data:
        cmd.extend(row)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    res = proc.stdout.strip()

    if proc.returncode == 1:
        if res == next_mode:
            main(next_mode)
        return

    paths_to_delete = res.split("|")
    if not paths_to_delete or paths_to_delete == [""]:
        return

    if (
        subprocess.run(
            [
                "zenity",
                "--question",
                "--text",
                f"Delete {len(paths_to_delete)} folders?",
            ],
            capture_output=True,
        ).returncode
        == 0
    ):
        for i, p in enumerate(paths_to_delete):
            if os.path.exists(p):
                shutil.rmtree(p)
        subprocess.run(["zenity", "--info", "--text", "Done!"])


if __name__ == "__main__":
    main()
