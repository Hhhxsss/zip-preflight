# zip-preflight

**在用户遇到 ZIP 文件名问题之前，先把问题找出来。**

这是一个用于发布包、数据集导出和上传流程的 ZIP 元数据检查工具。
它能提前发现 Windows 无法使用的文件名、大小写或 Unicode 重名、路径穿越等问题。
不解压、不修改、不上传文件；Python 3.10+，无运行时第三方依赖。

Windows 桌面入口支持 **右键检查单个 ZIP、结果窗口和保存报告**。
构建后的独立程序无需另外安装 Python，详见 [桌面使用说明](docs/windows-desktop.md)。

[English](README.md) · [规则说明](docs/rules.md) · [完整用法](docs/usage.md) · [项目调研](docs/research.md)

## 安装

从 GitHub 的版本标签安装，需要本机已安装 Git：

```console
python -m pip install "git+https://github.com/Hhhxsss/zip-preflight.git@v0.1.0"
```

也可以克隆后安装：

```console
git clone https://github.com/Hhhxsss/zip-preflight.git
cd zip-preflight
python -m pip install .
```

当前尚未发布到 PyPI。命令不在 PATH 时，可改用 `python -m zip_preflight`。
Windows、macOS、Linux 使用相同参数。

## Windows 桌面版与右键菜单

1. 把 `zip-preflight.exe` 放到准备长期保留的位置，双击打开。
2. 点击右下角 **右键菜单…**，确认启用；只为当前 Windows 用户注册，无需管理员权限。
3. 右键单个 ZIP，展开 **zip-preflight**，选择 **检查 ZIP** 或 **检查并保存报告…**。
   Windows 11 上可能需要先点击 **显示更多选项**。
4. 在结果窗口选择问题查看说明；点击 **保存报告…** 导出完整 JSON 或文本报告。

**不用时如何卸载：**打开程序，点击 **右键菜单…**，在“是否移除？”提示中选择 **是**。
看到移除成功提示后，关闭程序，再删除 EXE。卸载功能集成在同一个 EXE 内，
只删除本工具创建且带有归属标记的两个注册表分支，保留 ZIP 默认打开方式和已保存的报告。
直接删除 EXE 不会清理右键菜单；若已误删，可重新取得一份 EXE，用它移除菜单。

也可以使用 PowerShell。以下命令在项目根目录运行；若移动过 EXE，请替换为实际路径。
两条命令分别用于启用和移除菜单，按需要执行其中一条：

```powershell
& ".\dist\windows\zip-preflight.exe" --install-context-menu
& ".\dist\windows\zip-preflight.exe" --uninstall-context-menu
```

菜单记录的是 EXE 的绝对路径，移动程序后需要从新位置重新启用。
详细步骤见 [桌面使用说明](docs/windows-desktop.md)，
构建方法见 [生成 Windows EXE](docs/windows-desktop.md#build-a-standalone-windows-executable)，
注册表位置和菜单原理见 [右键菜单实现](docs/windows-desktop.md#how-the-menu-is-registered)。

## 快速使用

```console
zip-preflight release.zip
zip-preflight "dist/*.zip" --format json
zip-preflight dataset.zip --fail-on error
zip-preflight dataset.zip --max-total-size 21474836480 --max-ratio 2000
zip-preflight "dist/*.zip" --summary --max-findings 5
zip-preflight release.zip --config examples/zip-preflight.json
```

- 默认情况下，警告和错误都会让检查失败；`--fail-on error` 只让错误导致失败。
- 文件名匹配表达式建议加引号，工具会在各系统上自行展开；未匹配到文件会报错。
- 体积参数使用整数 **字节**，阈值可按项目需要调整。
- 返回码 `0` 表示通过当前策略，`1` 表示存在达到阈值的问题，`2` 表示输入或参数错误。

例如，包内同时存在 `Docs/a.txt` 和 `docs/b.txt` 时，即使文件名不同，
它们的隐含目录也会产生大小写冲突。`data/CON.csv` 则使用了 Windows 保留设备名。

## 配置文件与报告汇总

在当前工作目录放置 `.zip-preflight.json` 即可复用配置，命令行参数优先于文件中的值。
可参考 [完整示例](examples/zip-preflight.json)，用 `--config 路径` 指定其他文件，
或用 `--no-config` 跳过自动配置。配置支持体积与数量限制、失败策略、输出格式、
规则例外和汇总选项；未知字段或错误类型会直接报错。

`--summary` 按规则统计问题，每个压缩包默认展示前 5 条示例；
`--max-findings 0` 仅展示统计，`--no-summary` 恢复完整文本明细。
汇总不减少扫描条目，JSON 始终保留全部发现的问题。
`ignore_rules` 中的规则仍会被检查并显示，只是不参与通过或失败的判定。
完整优先级、字段和 JSON 汇总结构见 [使用指南](docs/usage.md#configuration-files)。

## 检查范围

| 类别 | 示例 |
| --- | --- |
| 路径风险 | `../escape`、`C:relative.txt`、绝对路径、UNC 路径 |
| Windows 兼容性 | `NUL.txt`、`COM¹`、冒号、文件名末尾的点或空格 |
| 目标冲突 | 同名条目、大小写重名、Unicode 规范化重名、文件与目录冲突 |
| 跨平台提醒 | 反斜杠、长路径、双向文本控制字符、加密和非通用压缩方法 |
| 资源策略 | 声明的总大小、单文件大小、条目数和压缩比超过阈值 |

默认总大小上限为 10 GiB，单条目为 2 GiB，条目数为 100,000，声明压缩比为 1000:1。
完整规则、严重级别和边界见 [规则文档](docs/rules.md)。

## 接入 CI

在生成 ZIP 文件之后加入以下步骤：

```yaml
- name: Install zip-preflight
  run: python -m pip install "git+https://github.com/Hhhxsss/zip-preflight.git@v0.1.0"
- name: Check release archives
  run: python -m zip_preflight "dist/*.zip"
```

更多示例，包括 JSON 输出、Python API、pre-commit 和 PowerShell，见 [使用指南](docs/usage.md)。

## 使用边界

本工具只检查 ZIP 中央目录元数据，不扫描病毒、不验证文件内容、CRC、本地文件头、
嵌套压缩包或符号链接目标。ZIP 声明的体积不等于实测解压体积，通过检查不代表可安全解压。

底层 `zipfile` 会先把中央目录读入内存，条目数上限无法限制这一步的内存分配。
处理不可信文件时，应由运行环境提供进程隔离、时间和内存限制。
文件名冲突模型采用 NFC、Unicode casefold 和末尾点/空格裁剪，属于保守兼容性策略，
不精确模拟任一文件系统。报告中包含路径和文件名，分享前请检查。

## 开发与贡献

```console
python -m pip install -e .
python -m unittest discover -s tests -v
```

欢迎提供可以复现的跨平台问题和最小测试样例，详见 [贡献指南](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)。相关开源工具和规则来源见 [项目调研](docs/research.md)。
