#!/usr/bin/env python3
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

VERSION = "1.0.0"
GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/nikolayli/steam_cleaner/main/cleaner.py"
)
STEAM_ROOT = os.path.expanduser("~/.steam/steam")
STEAMAPPS = os.path.join(STEAM_ROOT, "steamapps")
LOCALES = {
    "en": {
        "title": f"Steam Cleaner (v{VERSION})",
        "update_title": "Update available",
        "update_text": "New version {v} available (current: {cv}). Update?",
        "updated_text": "Updated! Please rerun the script.",
        "col_choice": "Choice",
        "col_name": "Name",
        "col_id": "ID",
        "col_size": "Size (MB)",
        "col_type": "Type",
        "col_path": "Path",
        "confirm_delete": "Delete {n} folders?",
        "done": "Done!",
        "lang_select": "Select Language / 选择语言",
    },
    "zh": {
        "title": f"Steam 清理工具 (v{VERSION})",
        "update_title": "有可用更新",
        "update_text": "发现新版本 {v}（当前版本：{cv}）。是否更新？",
        "updated_text": "更新完毕！请重新运行脚本。",
        "col_choice": "选择",
        "col_name": "游戏名称",
        "col_id": "AppID",
        "col_size": "大小 (MB)",
        "col_type": "类型",
        "col_path": "路径",
        "confirm_delete": "确认删除这 {n} 个文件夹吗？",
        "done": "完成！",
        "lang_select": "选择语言 / Select Language",
    },
}


def get_locale():
    sys_lang = locale.getdefaultlocale()[0]
    default = "zh" if sys_lang and sys_lang.startswith("zh") else "en"

    cmd = [
        "zenity",
        "--list",
        "--radiolist",
        "--title",
        "Language",
        "--column",
        "",
        "--column",
        "Language",
        "TRUE" if default == "en" else "FALSE",
        "English",
        "TRUE" if default == "zh" else "FALSE",
        "Chinese (中文)",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if "Chinese" in res.stdout:
        return LOCALES["zh"]
    return LOCALES["en"]


L = get_locale()


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
                            L["update_title"],
                            "--text",
                            L["update_text"].format(v=remote_version, cv=VERSION),
                        ]
                    )
                    if ask.returncode == 0:
                        with open(__file__, "w") as f:
                            f.write(content)
                        subprocess.run(
                            ["zenity", "--info", "--text", L["updated_text"]]
                        )
                        sys.exit(0)
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
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        return {}


def get_folder_size(path):
    try:
        total = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                total += os.path.getsize(os.path.join(root, f))
        return total // (1024 * 1024)
    except OSError:
        return 0


def collect_data(library_paths, api_names):
    combined_list = []
    for target_type in ["shadercache", "compatdata"]:
        target_dir = os.path.join(STEAMAPPS, target_type)
        if not os.path.exists(target_dir):
            continue
        for appid in os.listdir(target_dir):
            full_path = os.path.join(target_dir, appid)
            if not os.path.isdir(full_path) or not appid.isdigit():
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
            if not name:
                name = api_names.get(appid, "Unknown")
            if "Proton" in name or "Steam Linux Runtime" in name:
                continue
            size = get_folder_size(full_path)
            combined_list.append(
                ["FALSE", name, appid, str(size), target_type, full_path]
            )
    return sorted(combined_list, key=lambda x: x[1].lower())


def main():
    check_for_updates()
    libs = get_library_folders()
    api_names = get_steam_api_list()
    data = collect_data(libs, api_names)

    cmd = [
        "zenity",
        "--list",
        "--checklist",
        "--title",
        L["title"],
        "--width=1100",
        "--height=720",
        "--print-column=6",
        "--separator=|",
        f"--column={L['col_choice']}",
        f"--column={L['col_name']}",
        f"--column={L['col_id']}",
        f"--column={L['col_size']}",
        f"--column={L['col_type']}",
        f"--column={L['col_path']}",
    ]
    for row in data:
        cmd.extend(row)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return

    res = proc.stdout.strip()
    paths_to_delete = [p for p in res.split("|") if p]

    if paths_to_delete:
        confirm = subprocess.run(
            [
                "zenity",
                "--question",
                "--text",
                L["confirm_delete"].format(n=len(paths_to_delete)),
            ]
        )
        if confirm.returncode == 0:
            for p in paths_to_delete:
                if os.path.exists(p):
                    shutil.rmtree(p)
            subprocess.run(["zenity", "--info", "--text", L["done"]])


if __name__ == "__main__":
    main()
