"""Opt-in, current-user Windows ZIP menus; never change the ZIP default application."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

MENU_KEY = r"Software\Classes\SystemFileAssociations\.zip\shell\ZipPreflight"
COMMAND_KEY = r"Software\Classes\ZipPreflight.ContextMenu"
OWNED_KEYS = (MENU_KEY, COMMAND_KEY)
OWNER_VALUE = "ZipPreflightOwner"
OWNER = "zip-preflight.context-menu.v1"


def _registry():
    if sys.platform != "win32":
        raise OSError("右键菜单仅支持 Windows。")
    import winreg

    return winreg


def build_launch_command(executable: str, *, frozen: bool, save_after_scan: bool = False) -> str:
    arguments = [executable]
    if not frozen:
        arguments.extend(["-I", "-m", "zip_preflight.desktop"])
    if save_after_scan:
        arguments.append("--save-after-scan")
    arguments.append("--")
    # The Shell replaces %1 after parsing the template, so always quote it.
    return subprocess.list2cmdline(arguments) + ' "%1"'


def _owned(registry, path: str) -> bool:
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, path) as key:
            try:
                owner = registry.QueryValueEx(key, OWNER_VALUE)[0]
            except FileNotFoundError:
                owner = None
    except FileNotFoundError:
        return False
    if owner != OWNER:
        raise OSError("存在不属于 zip-preflight 的同名菜单，已停止操作。")
    return True


def _notify_shell() -> None:
    if sys.platform == "win32":
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def is_context_menu_installed() -> bool:
    registry = _registry()
    return all(_owned(registry, path) for path in OWNED_KEYS)


def _remove_tree(registry, path: str) -> None:
    if not any(path == root or path.startswith(root + "\\") for root in OWNED_KEYS):
        raise ValueError("Refusing to remove an unrelated registry key")
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, path) as key:
            children = []
            index = 0
            while True:
                try:
                    children.append(registry.EnumKey(key, index))
                    index += 1
                except OSError as error:
                    if getattr(error, "winerror", None) != 259:
                        raise
                    break
        for child in children:
            _remove_tree(registry, path + "\\" + child)
        registry.DeleteKey(registry.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        return


def install_context_menu() -> None:
    registry = _registry()
    existed = {path: _owned(registry, path) for path in OWNED_KEYS}
    frozen = bool(getattr(sys, "frozen", False))
    executable = Path(sys.executable).resolve()
    if not frozen:
        executable = executable.with_name("pythonw.exe")
        if not executable.is_file():
            raise OSError("找不到 Python 窗口启动程序，请使用桌面可执行程序安装右键菜单。")
        probe = subprocess.run(
            [str(executable), "-I", "-c", "import zip_preflight.desktop"],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if probe.returncode:
            raise OSError("请先将 zip-preflight 安装到当前 Python 环境，再启用右键菜单。")

    entries = {
        MENU_KEY: {
            OWNER_VALUE: OWNER,
            "MUIVerb": "zip-preflight",
            "MultiSelectModel": "Single",
            "ExtendedSubCommandsKey": "ZipPreflight.ContextMenu",
            "Icon": f'"{executable}",0',
        },
        COMMAND_KEY: {OWNER_VALUE: OWNER},
    }
    for verb, title, save in (("01check", "检查 ZIP", False), ("02save", "检查并保存报告…", True)):
        key = COMMAND_KEY + "\\shell\\" + verb
        entries[key] = {"MUIVerb": title, "MultiSelectModel": "Single"}
        entries[key + "\\command"] = {
            "": build_launch_command(str(executable), frozen=frozen, save_after_scan=save)
        }
    try:
        for path, values in entries.items():
            with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, path) as key:
                for name, value in values.items():
                    registry.SetValueEx(key, name, 0, registry.REG_SZ, value)
    except OSError:
        for path in reversed(OWNED_KEYS):
            if not existed[path]:
                _remove_tree(registry, path)
        raise
    _notify_shell()


def uninstall_context_menu() -> None:
    registry = _registry()
    # Check every owned root before modifying any key.
    existed = {path: _owned(registry, path) for path in OWNED_KEYS}
    for path in OWNED_KEYS:
        if existed[path]:
            _remove_tree(registry, path)
    _notify_shell()
