# zip-preflight

**在用户遇到 ZIP 文件名问题之前，先把问题找出来。**

这是一个用于发布包、数据集导出和上传流程的 ZIP 元数据检查工具。
它能提前发现 Windows 无法使用的文件名、大小写或 Unicode 重名、路径穿越等问题。
不解压、不修改、不上传文件；Python 3.10+，无运行时第三方依赖。

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

## 快速使用

```console
zip-preflight release.zip
zip-preflight "dist/*.zip" --format json
zip-preflight dataset.zip --fail-on error
zip-preflight dataset.zip --max-total-size 21474836480 --max-ratio 2000
```

- 默认情况下，警告和错误都会让检查失败；`--fail-on error` 只让错误导致失败。
- 文件名匹配表达式建议加引号，工具会在各系统上自行展开；未匹配到文件会报错。
- 体积参数使用整数 **字节**，阈值可按项目需要调整。
- 返回码 `0` 表示通过当前策略，`1` 表示存在达到阈值的问题，`2` 表示输入或参数错误。

例如，包内同时存在 `Docs/a.txt` 和 `docs/b.txt` 时，即使文件名不同，
它们的隐含目录也会产生大小写冲突。`data/CON.csv` 则使用了 Windows 保留设备名。

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
