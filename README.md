# maya_umbrella_scanner

面向 Windows 的便携式 Maya 场景病毒扫描与清理 CLI。发布包通过 PyOxidizer 内嵌运行时，用户机器不需要安装系统 Python；清理仍需要本机已安装的 Autodesk Maya，因为场景修复必须在所选版本的 `mayapy.exe` 和 Maya API 中执行。

## 安装

从 [GitHub Releases](https://github.com/loonghao/maya_umbrella_scanner/releases) 下载精确版本的 `maya_umbrella_scanner-<version>.zip` 和同一 Release 的 `SHA256SUMS`。校验 ZIP 的 SHA-256 后完整解压，保留 `maya_umbrella.exe`、`bin` 和 `lib` 的相对目录结构。它是一个无需外部 Python 的便携 CLI 包，不是单独一个可脱离配套文件运行的 PE。

安装 Agent Skill 后，也可以让 Agent 在取得精确版本和下载位置的批准后运行 Skill 自带的校验安装器：

```powershell
& "<skill-directory>\scripts\install_cli.ps1" -Version "<approved-version>"
```

安装器不会隐式选择 `latest`，不会覆盖已安装版本，并以 JSON 返回已验证的 `maya_umbrella.exe` 路径。它固定安装到 `%LOCALAPPDATA%\maya_umbrella_scanner\versions\<version>`，应以当前用户运行，不要使用提权的管理员 PowerShell。

## 用法

先确认便携 CLI 具备批量安全契约：

```powershell
.\maya_umbrella.exe --version
.\maya_umbrella.exe scan --help
.\maya_umbrella.exe clean --help
```

### 病毒扫描

重复 `--path` 可以扫描多个目录。程序递归检查目录下的 `.ma` 和 `.mb` 文件；扫描模式不会启动 Maya 或改写场景。

```powershell
.\maya_umbrella.exe scan `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --report "C:\temp\maya-umbrella-scan.json"
```

命中时，JSON 报告记录文件路径与源 SHA-256；stdout 中的 `report_file_sha256` 绑定报告的精确字节。计划清理时必须把报告、摘要、命中文件和目标范围一起交给用户明确批准。

### 自动杀毒

清理必须使用同一个 CLI、同一组路径、用户批准的原始报告与摘要，并指定本机 Maya 年份：

```powershell
.\maya_umbrella.exe clean `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --maya-version 2024 `
  --approved-scan-report "C:\temp\maya-umbrella-scan.json" `
  --approved-scan-report-sha256 "<approved-report-sha256>" `
  --confirm-clean `
  --report "C:\temp\maya-umbrella-clean.json"
```

没有批准证据的直接 `--maya-version` 调用会失败关闭。`--confirm-clean` 只是命令行门禁，不能代替用户对具体范围和副作用的知情批准。

清理会先把原场景备份到相邻的 `_virus` 目录，再原地保存修复后的场景，并在结束前重新扫描。请勿设置 `MAYA_UMBRELLA_IGNORE_BACKUP=true`。

Maya 打开场景后若以无回调的只读检查发现感染的引用文件，或发现批准场景清单之外的 Maya/Python 文件，本次清理会在场景改写前中止，并要求建立新的明确范围；清理引擎不会改写批准清单外的文件。

Maya 2019–2021 的 Python 2 无法通过当前引擎安全保存非 ASCII 场景路径；受控清理会在备份或启动 Maya 前拒绝该组合。不要在批准后移动或重命名文件；如改用其他 Maya 版本，必须重新扫描并批准。

## Agent Skill

仓库根目录遵循 [Agent Plugins 1.0](https://agent-plugins.org/specification)：`plugin.json` 描述完整插件包，`skills/maya-umbrella-batch-antivirus` 是可独立安装的 [Agent Skill](https://agentskills.io/specification)。Agent Plugins 规范只定义包格式，不规定安装或发布服务。

使用通用 Skills CLI 从 GitHub 安装指定 Skill（项目级安装请去掉 `--global`）：

```powershell
npx --yes skills@1.5.23 add loonghao/maya_umbrella_scanner `
  --skill maya-umbrella-batch-antivirus `
  --agent codex `
  --global `
  --yes
```

Skill 提供批量目录扫描、显式清理授权、备份哈希核验和清理后复扫。它只处理 Maya `.ma`/`.mb` 场景，不是通用系统杀毒软件。实际执行流程与风险边界见 `skills/maya-umbrella-batch-antivirus/SKILL.md`。

Agent 必须确认 `scan`/`clean` 子命令和两个批准参数都存在。v0.1.8 及更早版本不具备完整批量清理门禁，只能按旧版能力使用；Skill 会让不兼容版本在任何 Maya 场景被修改前失败关闭。每次 `--report` 都应使用一个尚不存在的 `.json` 路径，以保留独立审计证据；scan 在 stdout 输出的 `report_file_sha256` 必须与命中清单一起交给用户批准，并原样传给 clean。

为避免把任意现有项目子树从扫描范围隐藏，备份/隔离目录固定为 `_virus`。自定义 `MAYA_UMBRELLA_BACKUP_FOLDER_NAME` 现会失败关闭；这是新版的安全性 breaking change。

清理进程会预建空的 `Maya.env`，使用临时隔离的 `MAYA_APP_DIR`，并禁用 Python user-site；不会执行用户现有的 `Maya.env`、`userSetup.py`、`userSetup.mel`、`.pth`/`sitecustomize.py` 或自定义启动路径。只读检查可以报告相关 Maya/Python 目录中的匹配文件，但不会删除它们；这类文件需要另行批准检查和隔离，不能从场景复扫结果推断为安全。

### ClawHub

ClawHub 分发的是 Skill 子目录，不是仅含根 `plugin.json` 的完整 Agent Plugins 包。发布前先做 dry-run：

```powershell
npx --yes clawhub@0.23.3 skill publish .\skills\maya-umbrella-batch-antivirus `
  --owner loonghao `
  --categories security,operations `
  --topics maya,antivirus,malware,virus-scan,scene-cleanup `
  --dry-run `
  --json
```

正式发布前先执行 `npx --yes clawhub@0.23.3 login`。仓库配置 `CLAWHUB_TOKEN` secret 后，每个正式（非 prerelease）GitHub Release 会自动运行 `ClawHub Skill` workflow；`workflow_dispatch` 仅允许从 `main` 手动首发或受控补发。工作流固定使用 ClawHub CLI 0.23.3，首次发布时设置 `security,operations` 分类与检索 topics，后续同步省略这两个参数以保持内容未变化时的幂等性。它保存结构化回执，并把 `pending-publication` 或 `submitted` 作为“已提交、等待公开验证”，而不是误报成上传失败。公开版本通过安全审核并可见后，可通过 CLI 安装：

```powershell
openclaw skills install @loonghao/maya-umbrella-batch-antivirus
# 或使用 ClawHub registry CLI
npx --yes clawhub@0.23.3 install @loonghao/maya-umbrella-batch-antivirus
```

## 发布

版本与变更日志由 Release Please 从 Conventional Commits 统一维护。它同步 `pyproject.toml`、`maya_umbrella_scanner/__version__.py`、`plugin.json` 和 manifest，创建 `vX.Y.Z` 标签及 GitHub Release。标签工作流使用固定构建工具生成 Windows 便携包与 `SHA256SUMS`，只向 Release Please 已创建的 Release 附加资产。重跑不会覆盖已有资产；若上一次只成功上传 ZIP，会为该 ZIP 的确切字节补传校验文件，已有 ZIP 与校验文件不一致则失败关闭。

运行时架构及没有直接全面改写 Rust 的原因见 [ADR 0001](docs/adr/0001-portable-cli-runtime.md)。
