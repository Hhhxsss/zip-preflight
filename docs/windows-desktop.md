# Windows desktop and ZIP right-click menu

The desktop app checks one ZIP at a time, displays results in a native window,
and saves complete JSON or UTF-8 text reports. It uses the same scanner and JSON
schema as the CLI. Member payloads are never extracted or opened.

## Start the app

Download `zip-preflight.exe` from the
[v0.2.0 release](https://github.com/Hhhxsss/zip-preflight/releases/tag/v0.2.0),
or build it from source. The release executable targets Windows x64. No Python
installation is needed on the machine running that executable. Keep the file in
a stable location before enabling its right-click menu.

Alternatively, install the Python package in an environment with Tk support:

```console
python -m pip install .
zip-preflight-gui
python -m zip_preflight.desktop "release.zip"
```

On Windows the `zip-preflight-gui` entry point opens without a console window.
Omitting the ZIP path opens the window with a **选择 ZIP…** button. The app accepts
one ZIP path; use the CLI for multi-file automation.

## Enable the right-click menu

1. Open the desktop app and click **右键菜单…** in the lower right corner.
2. Answer **是** to **为当前 Windows 用户启用 ZIP 右键菜单？**.
3. Right-click one ZIP file and open **zip-preflight**:
   - **检查 ZIP** opens the result window and starts checking.
   - **检查并保存报告…** additionally opens the save dialog after checking.

On Windows 11 the menu may appear under **显示更多选项**. This first version uses
the classic cascading menu; it does not register a modern first-level Explorer
extension. Selecting multiple files hides the menu. ZIP extensions are matched
case-insensitively by the Windows file association.

You can also enable the menu from PowerShell. From the repository root:

```powershell
& ".\dist\windows\zip-preflight.exe" --install-context-menu
```

If you keep the executable elsewhere, replace the quoted path with its actual
location. The windowed executable displays a message box with the result.
Administrator rights are not needed. If you move the executable, enable the menu
again from its new location to update the registered path.

## Remove the menu and uninstall

The portable executable includes its own menu removal function; no separate
uninstaller is needed:

1. Open `zip-preflight.exe` and click **右键菜单…** in the lower right corner.
2. Answer **是** to **已启用右键菜单。是否移除？** and wait for the removal message.
3. Close the app, then delete `zip-preflight.exe` if you no longer need it.

Alternatively, remove the menu from PowerShell before deleting the executable:

```powershell
& ".\dist\windows\zip-preflight.exe" --uninstall-context-menu
```

This command removes the two registry branches listed below and their subkeys
only when they carry zip-preflight's ownership marker. It preserves other menus,
the default ZIP application, saved reports, and configuration files. Running it
again when the menu is already removed is harmless. Removal applies to the current
Windows user; use the same account that enabled the menu.

Deleting the executable alone leaves the menu registered. If you have already
deleted it, obtain another copy and run it with `--uninstall-context-menu`; removal
does not require the executable to be at its original location.

Installed Python users can manage the same menu with:

```powershell
python -m zip_preflight.desktop --install-context-menu
python -m zip_preflight.desktop --uninstall-context-menu
```

Remove the menu before uninstalling the Python package or deleting its environment.
An isolated import check prevents registering an uninstalled source checkout whose
GUI could not start from Explorer.

## How the menu is registered

The app uses Python's `winreg` module to create only these current-user branches:

```text
HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\.zip\shell\ZipPreflight
HKEY_CURRENT_USER\Software\Classes\ZipPreflight.ContextMenu
```

`MUIVerb` supplies the menu label, `ExtendedSubCommandsKey` links to the two child
commands, and `MultiSelectModel=Single` limits them to one selected file. The child
commands launch the registered executable with these argument templates:

```text
"<absolute path to zip-preflight.exe>" -- "%1"
"<absolute path to zip-preflight.exe>" --save-after-scan -- "%1"
```

Explorer replaces `%1` with the selected ZIP path. Quoting preserves paths with
spaces. The menu opens an independent window after a click; hovering expands the
choices. The app notifies Explorer after installing or removing the menu.

The registration follows Microsoft's [current-user cascading-menu guidance](https://learn.microsoft.com/en-us/windows/win32/shell/how-to-create-cascading-menus-with-the-extendedsubcommandskey-registry-entry)
and [single-selection verb model](https://learn.microsoft.com/en-us/windows/win32/shell/context-menu-handlers#employing-the-verb-selection-model).

## Read the results and save a report

Checks run in the background with a progress indicator. The window shows the
outcome, checked entry count, declared size, and error/warning/ignored counts.
Select an issue to see its filename, related filename, reason, and suggestion.
Control and bidirectional characters in names are escaped for display.

Long issue lists are paginated at 250 rows. **保存报告…** always exports the complete
result, including findings on other pages:

- Save as `.json` for the versioned CLI-compatible report with summaries.
- Save as `.txt` for a readable Chinese report with all issues and suggestions.

The filename defaults to `<archive>.zip-preflight.json` next to the ZIP. The save
dialog lets you choose another name or location. Existing reports are replaced
atomically after the new report is written; saving over the source archive or a
hardlink to it is rejected. Cancelling the save dialog keeps the result window open.
**复制结果** copies the complete readable report. Shortcuts are Ctrl+O (choose ZIP),
Ctrl+S (save), and Ctrl+Shift+C (copy report).

An unreadable ZIP produces a visible error that can also be exported. An incomplete
scan is explicitly labeled. Passing the check means passing the selected filename
and metadata policy; file contents and extraction safety are not established.

## Configuration

The desktop app uses built-in defaults regardless of Explorer's working directory.
It does not automatically load a configuration next to a downloaded archive. To
use a particular policy, start it with an explicit config:

```console
python -m zip_preflight.desktop --config examples/zip-preflight.json "release.zip"
```

Invalid configuration is displayed as an error and no scan report is generated.
See [configuration settings](usage.md#configuration-files) for accepted fields.

## Build a standalone Windows executable

Use a clean build environment to avoid unrelated packages from a system or Conda
installation. PyInstaller is a build-time tool, not a runtime package dependency.

```powershell
python -m venv .local/windows-build-env
.local\windows-build-env\Scripts\python -m pip install pyinstaller
.local\windows-build-env\Scripts\python tools/build_windows.py
```

The output is `dist/windows/zip-preflight.exe`. The build script uses PyInstaller's
`--onefile` option to bundle the Python interpreter, application code, and Tk into
one executable, and `--windowed` to start without a console window. Its entry point
is `tools/desktop_entry.py`. At startup the bundled runtime is unpacked into a
temporary directory; users do not need to install Python or PyInstaller.

Build on Windows; PyInstaller is not used as a cross compiler. Building the EXE
does not register a menu; enable it separately after placing it in a stable location.

Tests run with `python -m unittest discover -s tests -v`. Pure report and menu tests
use temporary files and an in-memory registry. Window tests exercise real Tk
widgets, background checking, paging, save/cancel/error handling, and both report
formats. Window tests skip when Tk or a graphical display is unavailable; routine
unit tests never modify the actual right-click menu.
