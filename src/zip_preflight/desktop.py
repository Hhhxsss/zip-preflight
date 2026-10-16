"""Desktop entry point and complete report exports; Tk is loaded only on demand."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .config import Settings, load_settings
from .models import Finding, Report
from .reporting import build_json_report, summarize

RULE_HELP = {
    "EMPTY_PATH": ("路径为空", "条目没有有效的相对文件名。", "删除该条目，或为它设置文件名。"),
    "ABSOLUTE_PATH": ("绝对路径", "路径包含盘符或从根目录开始。", "打包时使用相对路径。"),
    "PARENT_PATH": ("路径越界", "路径包含上级目录引用。", "移除路径中的 .. 组件。"),
    "BACKSLASH_PATH": (
        "路径分隔符不统一",
        "不同解压工具可能对反斜杠作不同处理。",
        "使用 / 分隔目录。",
    ),
    "NON_CANONICAL_PATH": (
        "路径不规范",
        "路径包含空组件、重复分隔符或当前目录引用。",
        "合并重复分隔符，并移除 ./。",
    ),
    "CONTROL_CHARACTER": ("隐藏控制字符", "文件名包含控制字符。", "移除换行、制表符等控制字符。"),
    "BIDI_CONTROL": (
        "文字方向控制字符",
        "文件名的显示顺序可能与实际内容不同。",
        "检查名称并移除方向控制字符。",
    ),
    "WINDOWS_CHARACTER": (
        "Windows 不支持的字符",
        "文件名包含 Windows 保留字符。",
        '替换 < > : " | ? * 等字符。',
    ),
    "WINDOWS_DEVICE": (
        "Windows 保留设备名",
        "路径使用了 Windows 设备名称。",
        "修改名称；添加扩展名仍可能不兼容。",
    ),
    "TRAILING_DOT_SPACE": (
        "名称末尾有点或空格",
        "部分工具会裁剪名称末尾的点或空格。",
        "移除末尾的点和空格。",
    ),
    "LONG_COMPONENT": ("单段名称过长", "某一文件名或目录名超过常见长度限制。", "缩短该段名称。"),
    "LONG_PATH": (
        "完整路径过长",
        "相对路径已达到旧版 Windows 路径长度限制。",
        "减少目录层级并缩短名称。",
    ),
    "SYMLINK": (
        "符号链接",
        "条目被标记为符号链接，链接目标未检查。",
        "确认交付是否需要链接，或使用普通文件。",
    ),
    "SPECIAL_FILE": ("特殊文件类型", "条目被标记为设备、管道等特殊类型。", "交付普通文件与目录。"),
    "ENCRYPTED_MEMBER": ("加密条目", "加密文件可能影响兼容性。", "确认接收方支持该加密方式。"),
    "COMPRESSION_METHOD": (
        "压缩方式兼容性",
        "压缩方式不是通用的 Stored 或 Deflate。",
        "确认解压工具支持，或改用 Deflate。",
    ),
    "MEMBER_SIZE_LIMIT": (
        "单文件过大",
        "声明的单文件大小超过本次检查限制。",
        "检查文件，或明确调整检查限制。",
    ),
    "COMPRESSION_RATIO": (
        "压缩比过高",
        "声明的解压体积与压缩体积比例异常高。",
        "核实内容与体积，再决定是否调整限制。",
    ),
    "DUPLICATE_ENTRY": ("重复条目", "压缩包中有完全相同的条目名称。", "移除重复条目后重新打包。"),
    "PATH_COLLISION": (
        "路径名称冲突",
        "路径在大小写、Unicode 或末尾裁剪规则下重名。",
        "统一名称拼写，或重命名冲突路径。",
    ),
    "FILE_DIRECTORY_CONFLICT": (
        "文件与目录冲突",
        "同一路径同时被用作文件与目录。",
        "重命名或移除冲突条目。",
    ),
    "TARGET_COLLISION": (
        "目标文件冲突",
        "不同条目可能落在同一个目标文件上。",
        "移除路径别名或重命名条目。",
    ),
    "ENTRY_COUNT_LIMIT": (
        "条目数量超限",
        "只检查了限制以内的条目，本次扫描不完整。",
        "检查条目数量，或调整上限后重新检查。",
    ),
    "TOTAL_SIZE_LIMIT": (
        "总大小超限",
        "声明的解压总大小超过本次检查限制。",
        "核实内容与体积，或调整总大小上限。",
    ),
}


def display_text(value: str) -> str:
    """Keep readable Unicode while exposing controls and direction-changing marks."""
    return "".join(
        char if char.isprintable() else json.dumps(char, ensure_ascii=True)[1:-1] for char in value
    )


def finding_details(finding: Finding, settings: Settings) -> str:
    title, reason, advice = RULE_HELP.get(
        finding.code, (finding.code, finding.message, "检查该条目后重新打包。")
    )
    severity = "错误" if finding.severity == "error" else "警告"
    if finding.code in settings.ignore_rules:
        severity += "（已忽略，不影响本次通过判定）"
    lines = [f"{severity} · {title}"]
    if finding.member is not None:
        lines.append(f"文件：{display_text(finding.member)}")
    if finding.related_member is not None:
        lines.append(f"关联文件：{display_text(finding.related_member)}")
    if finding.entry_index is not None:
        lines.append(f"条目序号：{finding.entry_index + 1}")
    lines.extend([f"原因：{reason}", f"建议：{advice}"])
    return "\n".join(lines)


def text_report(report: Report, settings: Settings) -> str:
    total = summarize([report], settings.fail_on, ignore_rules=settings.ignore_rules)
    status = (
        "无法读取"
        if report.error
        else "未通过"
        if report.fails(settings.fail_on, ignore_rules=settings.ignore_rules)
        else "通过"
    )
    lines = [
        "zip-preflight ZIP 检查报告",
        f"结果：{status}",
        f"文件：{display_text(report.archive)}",
        f"已检查：{report.checked_entries}/{report.entry_count} 个条目",
        f"扫描完整：{'是' if report.scan_complete else '否'}",
        f"声明的解压大小：{report.declared_uncompressed_bytes} 字节",
        f"错误：{total['errors']}；警告：{total['warnings']}；已忽略：{total['ignored_findings']}",
        f"失败策略：{'错误与警告' if settings.fail_on == 'warning' else '仅错误'}",
        f"规则例外：{', '.join(settings.ignore_rules) or '无'}",
    ]
    if report.error:
        lines.append(f"读取错误：{display_text(report.error)}")
    for rule in total["by_rule"]:
        title = RULE_HELP.get(rule["code"], (rule["code"],))[0]
        ignored = "（已忽略）" if rule["ignored"] else ""
        lines.append(f"{title}：{rule['count']} 条{ignored}")
    lines.extend(["", "问题明细："])
    for index, finding in enumerate(report.findings, start=1):
        lines.extend([f"\n{index}. {finding_details(finding, settings)}"])
    if not report.findings:
        lines.append("没有发现问题。" if not report.error else "本次未完成检查。")
    lines.extend(["", "本工具只检查文件名与压缩包声明的信息，未验证文件内容。"])
    return "\n".join(lines) + "\n"


def save_report(destination: str | os.PathLike[str], report: Report, settings: Settings) -> None:
    """Atomically save every finding; refuse to replace the archive or its aliases."""
    path = Path(destination).resolve()
    source = Path(report.archive).resolve()
    if path == source or (path.exists() and source.exists() and os.path.samefile(path, source)):
        raise ValueError("报告不能覆盖正在检查的 ZIP 文件。")
    if path.suffix.lower() == ".json":
        data = build_json_report(
            [report],
            limits=settings.limits,
            fail_on=settings.fail_on,
            ignore_rules=settings.ignore_rules,
            summary=True,
        )
        content = json.dumps(data, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
    elif path.suffix.lower() == ".txt":
        content = text_report(report, settings)
    else:
        raise ValueError("请选择 .json 或 .txt 作为报告文件扩展名。")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".zip-preflight-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def desktop_settings(config_path: str | None = None) -> Settings:
    # Explorer's working directory must never select the desktop pass/fail policy.
    return load_settings({}, config_path=config_path, no_config=config_path is None)


def _startup_message(message: str, *, error: bool = False) -> None:
    if sys.platform == "win32" and (getattr(sys, "frozen", False) or sys.stdout is None):
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "zip-preflight", 0x10 if error else 0x40)
    else:
        print(message, file=sys.stderr if error else sys.stdout)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="zip-preflight desktop ZIP checker")
    parser.add_argument("archive", nargs="?", help="One ZIP path; omit to select a file")
    parser.add_argument("--config", help="Explicit JSON config; desktop defaults ignore the cwd")
    parser.add_argument("--save-after-scan", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--install-context-menu", action="store_true")
    action.add_argument("--uninstall-context-menu", action="store_true")
    args = parser.parse_args(argv)
    if args.install_context_menu or args.uninstall_context_menu:
        if args.archive or args.config or args.save_after_scan:
            parser.error("menu installation cannot be combined with a ZIP check")
        from . import windows_shell

        try:
            if args.install_context_menu:
                windows_shell.install_context_menu()
                _startup_message(
                    "已启用 zip-preflight 右键菜单。Windows 11 可能显示在“显示更多选项”中。"
                )
            else:
                windows_shell.uninstall_context_menu()
                _startup_message("已移除 zip-preflight 右键菜单。")
            return 0
        except (OSError, ValueError) as error:
            _startup_message(str(error), error=True)
            return 2
    try:
        import tkinter as tk

        from .desktop_ui import ResultWindow
    except ImportError as error:
        _startup_message(
            f"无法启动结果窗口：{error}。请安装带 Tk 支持的 Python 或使用桌面版程序。", error=True
        )
        return 2
    try:
        root = tk.Tk()
    except tk.TclError as error:
        _startup_message(f"无法启动结果窗口：{error}", error=True)
        return 2
    app = ResultWindow(root, config_path=args.config, save_after_scan=args.save_after_scan)
    if args.archive:
        root.after(50, app.inspect, args.archive)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
