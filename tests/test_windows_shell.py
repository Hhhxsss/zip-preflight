from __future__ import annotations

import unittest
from unittest.mock import patch

from zip_preflight import windows_shell as shell


class Key:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class MemoryRegistry:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.keys = {}
        self.deleted = []

    def OpenKey(self, hive, path):
        assert hive == self.HKEY_CURRENT_USER
        if path not in self.keys:
            raise FileNotFoundError(path)
        return Key(path)

    def CreateKeyEx(self, hive, path):
        assert hive == self.HKEY_CURRENT_USER
        parts = path.split("\\")
        for end in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:end]), {})
        return Key(path)

    def SetValueEx(self, key, name, _reserved, kind, value):
        assert kind == self.REG_SZ
        self.keys[key.path][name] = value

    def QueryValueEx(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(name)
        return self.keys[key.path][name], self.REG_SZ

    def EnumKey(self, key, index):
        prefix = key.path + "\\"
        children = sorted(
            {path[len(prefix) :].split("\\")[0] for path in self.keys if path.startswith(prefix)}
        )
        if index >= len(children):
            error = OSError("No more data")
            error.winerror = 259
            raise error
        return children[index]

    def DeleteKey(self, hive, path):
        assert hive == self.HKEY_CURRENT_USER
        assert not any(key.startswith(path + "\\") for key in self.keys)
        del self.keys[path]
        self.deleted.append(path)


class WindowsShellTests(unittest.TestCase):
    def setUp(self):
        self.registry = MemoryRegistry()
        for target, kwargs in (
            ("zip_preflight.windows_shell._registry", {"return_value": self.registry}),
            ("zip_preflight.windows_shell._notify_shell", {}),
            ("zip_preflight.windows_shell.sys.frozen", {"new": True, "create": True}),
            (
                "zip_preflight.windows_shell.sys.executable",
                {"new": r"C:\应用 文件\zip-preflight.exe"},
            ),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_commands_quote_the_archive_and_support_spaces_without_a_shell(self):
        command = shell.build_launch_command(r"C:\应用 文件\app.exe", frozen=True)
        self.assertEqual('"C:\\应用 文件\\app.exe" -- "%1"', command)
        command = shell.build_launch_command(
            "C:\\Python\\pythonw.exe", frozen=False, save_after_scan=True
        )
        self.assertIn("-I -m zip_preflight.desktop --save-after-scan --", command)
        self.assertTrue(command.endswith(' "%1"'))

    def test_install_creates_only_current_user_zip_menu_and_two_actions(self):
        shell.install_context_menu()
        self.assertTrue(shell.is_context_menu_installed())
        menu = self.registry.keys[shell.MENU_KEY]
        self.assertEqual("Single", menu["MultiSelectModel"])
        self.assertEqual("ZipPreflight.ContextMenu", menu["ExtendedSubCommandsKey"])
        for verb in ("01check", "02save"):
            command = self.registry.keys[shell.COMMAND_KEY + "\\shell\\" + verb + "\\command"][""]
            self.assertTrue(command.endswith(' "%1"'))
            self.assertEqual(verb == "02save", "--save-after-scan" in command)
        self.assertNotIn("Software\\Classes\\.zip", self.registry.keys)

    def test_install_is_repeatable_and_uninstall_preserves_unrelated_entries(self):
        self.registry.keys["Software\\Classes\\OtherApp"] = {"name": "keep"}
        shell.install_context_menu()
        before = dict(self.registry.keys)
        shell.install_context_menu()
        self.assertEqual(before, self.registry.keys)
        shell.uninstall_context_menu()
        shell.uninstall_context_menu()
        self.assertFalse(shell.is_context_menu_installed())
        self.assertEqual({"name": "keep"}, self.registry.keys["Software\\Classes\\OtherApp"])
        self.assertTrue(
            all(
                any(key == root or key.startswith(root + "\\") for root in shell.OWNED_KEYS)
                for key in self.registry.deleted
            )
        )

    def test_foreign_registration_is_not_overwritten_or_removed(self):
        self.registry.keys[shell.MENU_KEY] = {"MUIVerb": "Other application"}
        with self.assertRaises(OSError):
            shell.install_context_menu()
        with self.assertRaises(OSError):
            shell.uninstall_context_menu()
        self.assertEqual({"MUIVerb": "Other application"}, self.registry.keys[shell.MENU_KEY])

    def test_fresh_install_rolls_back_on_write_failure(self):
        original = self.registry.SetValueEx

        def fail_command(key, name, *args):
            if key.path.endswith("\\command"):
                raise OSError("access denied")
            original(key, name, *args)

        with patch.object(self.registry, "SetValueEx", side_effect=fail_command):
            with self.assertRaises(OSError):
                shell.install_context_menu()
        self.assertFalse(any(root in self.registry.keys for root in shell.OWNED_KEYS))

    def test_delete_guard_rejects_unrelated_registry_paths(self):
        with self.assertRaises(ValueError):
            shell._remove_tree(self.registry, "Software\\Classes\\OtherApp")


if __name__ == "__main__":
    unittest.main()
