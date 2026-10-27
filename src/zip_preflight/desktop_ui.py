"""A small native result window. Workers never call Tk or block Explorer."""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

from . import __version__
from .config import Settings
from .desktop import (
    RULE_HELP,
    desktop_settings,
    display_text,
    finding_details,
    save_report,
    text_report,
)
from .models import Report
from .reporting import summarize
from .scanner import scan_archive

PAGE_SIZE = 250


class ResultWindow:
    def __init__(self, root, *, config_path: str | None = None, save_after_scan: bool = False):
        import tkinter as tk
        from tkinter import font, ttk

        self.root = root
        self.config_path = config_path
        self.save_after_scan = save_after_scan
        self.report: Report | None = None
        self.settings = Settings()
        self.busy = False
        self.closed = False
        self.page = 0
        self.events: queue.Queue = queue.Queue()
        root.title(f"zip-preflight {__version__} · ZIP 检查")
        root.geometry("1040x760")
        root.minsize(850, 620)
        root.configure(background="#f3f5f7")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-o>", lambda _event: self.choose_archive() if not self.busy else None)
        root.bind("<Control-s>", lambda _event: self.save())
        root.bind("<Control-Shift-C>", lambda _event: self.copy())
        font.nametofont("TkDefaultFont").configure(family="Microsoft YaHei UI", size=10)
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(
            "Treeview", rowheight=font.nametofont("TkDefaultFont").metrics("linespace") + 12
        )
        style.configure("Heading.TLabel", font=("Microsoft YaHei UI", 12, "bold"))

        outer = ttk.Frame(root, padding=24)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="zip-preflight", font=("Microsoft YaHei UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        buttons = ttk.Frame(header)
        buttons.grid(row=0, column=1, sticky="e")
        self.open_button = ttk.Button(buttons, text="选择 ZIP…", command=self.choose_archive)
        self.open_button.pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(buttons, text="保存报告…", command=self.save)
        self.save_button.pack(side="left", padx=(0, 8))
        self.copy_button = ttk.Button(buttons, text="复制结果", command=self.copy)
        self.copy_button.pack(side="left")

        self.filename = tk.StringVar(value="选择一个 ZIP，或在文件上右键使用 zip-preflight。")
        ttk.Label(outer, textvariable=self.filename, wraplength=950).grid(
            row=1, column=0, sticky="ew", pady=(10, 16)
        )
        status = ttk.Frame(outer)
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        self.status = tk.StringVar(value="准备检查")
        self.status_label = ttk.Label(status, textvariable=self.status, style="Heading.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")
        self.counts = tk.StringVar(value="错误 0    警告 0    已忽略 0")
        ttk.Label(status, textvariable=self.counts).grid(row=0, column=1, sticky="e")
        self.scan_info = tk.StringVar(value="使用标准规则：错误与警告均影响通过判定。")
        ttk.Label(status, textvariable=self.scan_info).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        table = ttk.Frame(outer)
        table.grid(row=4, column=0, sticky="nsew", pady=(16, 8))
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table, columns=("severity", "problem", "member"), show="headings", selectmode="browse"
        )
        for name, title, width in (
            ("severity", "级别", 85),
            ("problem", "问题", 220),
            ("member", "文件或目录", 580),
        ):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=60, stretch=name == "member")
        self.tree.tag_configure("error", foreground="#b42318")
        self.tree.tag_configure("warning", foreground="#965b00")
        self.tree.tag_configure("ignored", foreground="#667085")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.select_finding)

        paging = ttk.Frame(outer)
        paging.grid(row=5, column=0, sticky="ew")
        paging.columnconfigure(0, weight=1)
        self.page_info = tk.StringVar(value="检查结果会显示在这里。")
        ttk.Label(paging, textvariable=self.page_info).grid(row=0, column=0, sticky="w")
        self.previous_button = ttk.Button(
            paging, text="上一页", command=lambda: self.change_page(-1)
        )
        self.previous_button.grid(row=0, column=1, padx=6)
        self.next_button = ttk.Button(paging, text="下一页", command=lambda: self.change_page(1))
        self.next_button.grid(row=0, column=2)
        ttk.Label(outer, text="问题说明与处理建议", style="Heading.TLabel").grid(
            row=6, column=0, sticky="w", pady=(18, 8)
        )
        self.details = tk.Text(
            outer,
            height=7,
            wrap="word",
            relief="solid",
            borderwidth=1,
            background="#ffffff",
            foreground="#263244",
            padx=12,
            pady=10,
            font=font.nametofont("TkDefaultFont"),
        )
        self.details.grid(row=7, column=0, sticky="ew")
        self._details("选择一条问题，查看原因与处理建议。")

        footer = ttk.Frame(outer)
        footer.grid(row=8, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        self.note = tk.StringVar(value="仅检查文件名与压缩包声明的信息，未验证文件内容。")
        ttk.Label(footer, textvariable=self.note, wraplength=730).grid(row=0, column=0, sticky="w")
        if sys.platform == "win32":
            ttk.Button(footer, text="右键菜单…", command=self.manage_menu).grid(
                row=0, column=1, sticky="e"
            )
        self._buttons()
        self.poll_id = root.after(80, self._poll)

    def _details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _buttons(self) -> None:
        self.open_button.state(["disabled"] if self.busy else ["!disabled"])
        enabled = self.report is not None and not self.busy
        for button in (self.save_button, self.copy_button):
            button.state(["!disabled"] if enabled else ["disabled"])
        count = len(self.report.findings) if self.report else 0
        self.previous_button.state(
            ["!disabled"] if not self.busy and self.page > 0 else ["disabled"]
        )
        self.next_button.state(
            ["!disabled"] if not self.busy and (self.page + 1) * PAGE_SIZE < count else ["disabled"]
        )

    def choose_archive(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择要检查的 ZIP 文件",
            filetypes=[("ZIP 压缩包", "*.zip *.ZIP")],
        )
        if path:
            self.inspect(path)

    def inspect(self, path: str) -> None:
        if self.busy or self.closed:
            return
        archive = str(Path(path).resolve())
        self.report = None
        self.busy = True
        self.page = 0
        self.filename.set(display_text(archive))
        self.status.set("正在检查…")
        self.status_label.configure(foreground="#344054")
        self.counts.set("错误 —    警告 —    已忽略 —")
        self.scan_info.set("正在读取压缩包信息，请稍候。")
        self.note.set("检查在后台执行，可以关闭窗口。")
        self._details("检查完成后，这里会显示问题说明与处理建议。")
        self.tree.delete(*self.tree.get_children())
        self.page_info.set("正在检查…")
        self.progress.grid()
        self.progress.start(12)
        self._buttons()

        def worker():
            try:
                settings = desktop_settings(self.config_path)
                report = scan_archive(archive, limits=settings.limits)
                self.events.put(("scan", (report, settings)))
            except Exception as error:
                self.events.put(("error", display_text(str(error))))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        if self.closed:
            return
        try:
            kind, result = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            self.progress.grid_remove()
            if kind == "scan":
                self.report, self.settings = result
                self._show_report()
                if self.save_after_scan:
                    self.save_after_scan = False
                    self.root.after_idle(self.save)
            elif kind == "saved":
                self.note.set(f"报告已保存：{display_text(result)}")
            elif kind == "save_error":
                self._details(result)
                self.note.set("报告未保存，请检查文件名或写入权限后重试。")
            else:
                self.status.set("检查或保存未完成")
                self.status_label.configure(foreground="#b42318")
                self._details(result)
                self.note.set("请检查文件路径、配置或写入权限后重试。")
            self._buttons()
        self.poll_id = self.root.after(80, self._poll)

    def _show_report(self) -> None:
        report = self.report
        total = summarize([report], self.settings.fail_on, ignore_rules=self.settings.ignore_rules)
        if report.error:
            status, color = "无法读取 ZIP", "#b42318"
            self._details(display_text(report.error))
        elif not report.scan_complete:
            status, color = "检查未完成 · 条目数量超限", "#b42318"
        elif report.fails(self.settings.fail_on, ignore_rules=self.settings.ignore_rules):
            status, color = "发现需要处理的问题", "#b42318" if total["errors"] else "#965b00"
        else:
            status, color = "通过本次检查", "#087443"
        self.status.set(status)
        self.status_label.configure(foreground=color)
        self.counts.set(
            f"错误 {total['errors']}    警告 {total['warnings']}    "
            f"已忽略 {total['ignored_findings']}"
        )
        self.scan_info.set(
            f"已检查 {report.checked_entries:,} / {report.entry_count:,} 个条目 · "
            f"声明的解压大小 {report.declared_uncompressed_bytes:,} 字节"
        )
        self.note.set("仅检查文件名与压缩包声明的信息，未验证文件内容。")
        self.render_page()

    def render_page(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if self.report is None:
            return
        findings = self.report.findings
        start = self.page * PAGE_SIZE
        for index in range(start, min(start + PAGE_SIZE, len(findings))):
            finding = findings[index]
            ignored = finding.code in self.settings.ignore_rules
            tag = "ignored" if ignored else finding.severity
            level = "已忽略" if ignored else "错误" if finding.severity == "error" else "警告"
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    level,
                    RULE_HELP.get(finding.code, (finding.code,))[0],
                    display_text(finding.member) if finding.member is not None else "整个压缩包",
                ),
                tags=(tag,),
            )
        if findings:
            self.page_info.set(
                f"显示 {start + 1}–{min(start + PAGE_SIZE, len(findings))} / "
                f"共 {len(findings):,} 条问题；保存报告将包含全部明细。"
            )
            self.tree.selection_set(str(start))
            self.select_finding()
        else:
            self.page_info.set("没有问题明细。" if self.report.error else "未发现需要处理的问题。")
            if not self.report.error:
                self._details("没有发现问题。你可以保存本次检查报告。")
        self._buttons()

    def change_page(self, delta: int) -> None:
        if self.busy or self.report is None:
            return
        target = self.page + delta
        if 0 <= target <= max(0, (len(self.report.findings) - 1) // PAGE_SIZE):
            self.page = target
            self.render_page()

    def select_finding(self, _event=None) -> None:
        selection = self.tree.selection()
        if selection and self.report is not None:
            self._details(finding_details(self.report.findings[int(selection[0])], self.settings))

    def save(self) -> None:
        from tkinter import filedialog

        if self.report is None or self.busy:
            return
        archive = Path(self.report.archive)
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="保存完整检查报告",
            initialdir=str(archive.parent),
            initialfile=archive.stem + ".zip-preflight.json",
            defaultextension=".json",
            filetypes=[("JSON 报告", "*.json"), ("文本报告", "*.txt")],
        )
        if not path:
            return
        self.busy = True
        self.progress.grid()
        self.progress.start(12)
        self.note.set("正在保存完整报告…")
        self._buttons()

        def worker():
            try:
                save_report(path, self.report, self.settings)
                self.events.put(("saved", path))
            except (OSError, ValueError) as error:
                self.events.put(("save_error", display_text(str(error))))

        threading.Thread(target=worker, daemon=True).start()

    def copy(self) -> None:
        if self.report is not None and not self.busy:
            self.root.clipboard_clear()
            self.root.clipboard_append(text_report(self.report, self.settings))
            self.note.set("完整检查结果已复制。")

    def manage_menu(self) -> None:
        from tkinter import messagebox

        from . import windows_shell

        try:
            installed = windows_shell.is_context_menu_installed()
            if installed:
                if not messagebox.askyesno(
                    "右键菜单", "已启用右键菜单。是否移除？", parent=self.root
                ):
                    return
                windows_shell.uninstall_context_menu()
                message = "已移除右键菜单。"
            else:
                if not messagebox.askyesno(
                    "右键菜单", "为当前 Windows 用户启用 ZIP 右键菜单？", parent=self.root
                ):
                    return
                windows_shell.install_context_menu()
                message = "已启用右键菜单。Windows 11 可能显示在“显示更多选项”中。"
            messagebox.showinfo("zip-preflight", message, parent=self.root)
        except (OSError, ValueError) as error:
            messagebox.showerror("右键菜单未更新", str(error), parent=self.root)

    def close(self) -> None:
        self.closed = True
        self.root.after_cancel(self.poll_id)
        self.root.destroy()
