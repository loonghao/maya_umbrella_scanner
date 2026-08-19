# Maya Umbrella Scanner — Autodesk Maya 场景病毒扫描器

[English](README.md) | [简体中文](README.zh-CN.md)

`maya_umbrella_scanner` 是面向 Windows x64 的便携式 CLI 与 Agent Skill，用于批量扫描 Autodesk Maya `.ma` 和 `.mb` 场景中的已知恶意代码，并在获得批准后执行受控清理。

> [!TIP]
> **已支持 Agent Skills。** 如果所用 Codex、WorkBuddy 或其他客户端版本支持 Agent Skills，即可安装 `maya-umbrella-batch-antivirus` 并用自然语言发起 Maya 病毒扫描。Skill 会串联范围确认、批量扫描、命中披露、明确清理授权、备份校验和独立的清理后复扫，可以在保留安全门禁的同时减少手工步骤。

## Maya Umbrella Scanner 是什么？

Maya Umbrella Scanner 是面向 Windows x64 的批量 Maya 病毒扫描器与受控 Maya 病毒查杀流程。它递归检查用户精确指定的目录，查找 Maya 场景文件中的已知病毒特征。扫描模式不会启动 Maya 或改写场景。只有在披露并批准命中项后，清理流程才会通过所选本地 Maya 安装的 `mayapy.exe` 和 Maya API 修复受影响的场景。

PyOxidizer 发布包内嵌 Python 运行时，因此扫描不需要系统 Python。清理仍需要本机安装本次操作明确选择的 Autodesk Maya 年份。

> [!IMPORTANT]
> 本项目只处理 Maya `.ma` 和 `.mb` 场景病毒，不是通用系统杀毒软件。场景扫描结果干净，也不能证明 Maya 启动目录、Maya 安装、引用文件或 Windows 其他位置没有问题。

## 项目组成

| 名称 | 作用 |
| --- | --- |
| Maya Umbrella Scanner / `maya_umbrella_scanner` | 产品与仓库名称 |
| `maya_umbrella.exe` | Windows x64 便携式批量 CLI |
| `maya-umbrella-scanner` | [`plugin.json`](plugin.json) 声明的 Agent Plugin 名称 |
| `maya-umbrella-batch-antivirus` | 可安装的 [Agent Skill](skills/maya-umbrella-batch-antivirus/SKILL.md) |

## 核心能力

- 通过重复 `--path`，一次扫描多个明确选择的目录。
- 在扫描模式下递归检查 Maya `.ma` 和 `.mb` 文件，不启动 Maya。
- 将清理授权绑定到同一可执行文件、目标集合、报告字节、感染路径和源文件 SHA-256。
- 在改写任何场景前，先在相邻 `_virus` 目录建立经过验证且不可覆盖的备份。
- 将 Maya 清理与现有启动钩子隔离，并以全范围终检和独立的清理后复扫结束流程。
- 允许支持 Agent Skills 的客户端（包括具备该能力的 Codex 或 WorkBuddy 版本）通过边界明确的 Agent Skill 编排完整流程。

## 环境要求

| 任务 | 要求 |
| --- | --- |
| 扫描 | Windows x64 发布包；不需要系统 Python 或 Autodesk Maya。 |
| 清理 | 同一个发布包，以及本机安装的、此次操作明确选择年份的 Autodesk Maya。 |
| 使用 `npx` 安装 Skill | 仅此安装方式需要 Node.js 和 npm，扫描器运行时不需要。 |
| 使用 Skill 自带 CLI 安装器 | Windows PowerShell 5.1 或更高版本、`%LOCALAPPDATA%`，并使用当前非管理员用户。 |

## 安装

### 安装 Agent Skill

使用 Skills CLI 安装仓库中的 Skill。以下命令以 Codex 全局安装为例；项目级安装请去掉 `--global`：

```powershell
npx --yes skills@1.5.23 add loonghao/maya_umbrella_scanner `
  --skill maya-umbrella-batch-antivirus `
  --agent codex `
  --global `
  --yes
```

对于支持 Agent Skills 的 WorkBuddy 或其他 Agent，请通过该客户端支持的 Skills 入口导入同一个 `maya-umbrella-batch-antivirus` Skill。上面的命令仅是 Codex 示例。

如果尚未安装兼容 CLI，Skill 会先展示精确仓库、Release 版本、ZIP 资产、校验文件和安装目标。得到下载批准后，它才会用精确版本运行经过校验的安装器：

```powershell
& "<skill-directory>\scripts\install_cli.ps1" -Version "<approved-version>"
```

安装器不会选择 `latest`，不会覆盖已安装版本，并以 JSON 返回经过验证的 `maya_umbrella.exe` 路径。它固定安装到 `%LOCALAPPDATA%\maya_umbrella_scanner\versions\<version>`。必须以当前非提权用户运行；禁止从管理员 PowerShell 执行。

### 手动安装便携 CLI

从同一个 [GitHub Release](https://github.com/loonghao/maya_umbrella_scanner/releases) 下载精确版本的 `maya_umbrella_scanner-<version>.zip` 和 `SHA256SUMS`。验证 ZIP 的 SHA-256 后，再完整解压。

必须保留 `maya_umbrella.exe`、`bin` 和 `lib` 的相对目录结构。该压缩包是便携式 CLI 套件，不是可脱离配套文件单独运行的 PE。

## 如何扫描并清理 Maya 场景病毒

### 通过支持 Agent Skills 的客户端使用（Codex、WorkBuddy 等）

安装 Skill 后，提交边界明确的自然语言请求：

```text
使用 maya-umbrella-batch-antivirus Skill 扫描 C:\project\scenes 中的 Maya 场景病毒。
先向我展示命中项和报告；未经我明确批准，不要清理任何内容。
```

意图只用于选择 Skill，并不代表授权清理。即使请求中写了“清理”“删除”或“杀毒”，Skill 也必须先扫描、披露精确命中和副作用，再等待明确批准。

### 验证 CLI 契约

要求 v0.2.0 批量契约引入的批量命令与批准参数。不要只相信版本字符串，必须探测实际能力：

```powershell
.\maya_umbrella.exe --version
.\maya_umbrella.exe scan --help
.\maya_umbrella.exe clean --help
```

可执行文件必须暴露 `scan`、`clean`、`--approved-scan-report` 和 `--approved-scan-report-sha256`。Skill 必须拒绝缺少该契约的版本（包括 v0.1.8 及更早版本），且绝不能回退到旧版单根目录接口。

### 扫描 Maya 场景

重复 `--path` 可以扫描多个精确目录。每次提供 `--report` 时都必须使用尚不存在的全新 `.json` 路径；后续可能清理时必须生成报告：

```powershell
.\maya_umbrella.exe scan `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --report "C:\temp\maya-umbrella-scan.json"
```

报告记录每个感染路径与源文件 SHA-256。stdout JSON 中的 `report_file_sha256` 绑定报告的精确字节。清理前必须披露解析后的根目录、扫描器路径与版本、感染文件清单、源哈希、报告 SHA-256、所选 Maya 年份和清理副作用。

扫描模式不会启动 Maya 或改写场景，但可能创建临时输出和指定的报告。异常宽泛的扫描根目录只有在该精确范围得到确认后才能使用。

### 仅在获得明确批准后清理

用户批准已披露的命中项和副作用后，使用同一个可执行文件、同一组路径、未经改动的已批准报告及其 `report_file_sha256`，以及一个明确选择的 Maya 年份：

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

`--confirm-clean` 只是 CLI 门禁，不能代替用户对精确范围和副作用的知情批准。即使用户要求，清理目标也不能是盘符根目录或用户主目录。清理还会拒绝符号链接、junction 和 reparse point。

清理会先建立并验证相邻的 `_virus` 备份，再强制原地保存修复后的场景。遇到内容漂移、备份冲突、文件身份别名、哈希不一致、证据不足或 `indeterminate`（无法确定）的目标时，流程会中止。

清理期间不得有交互式 Maya 会话并发编辑目标场景。清理后，还必须使用同一个可执行文件、同一组路径和第三个全新报告，额外执行一次独立扫描：

```powershell
.\maya_umbrella.exe scan `
  --path "C:\project\scenes" `
  --path "D:\shots\asset" `
  --report "C:\temp\maya-umbrella-post-clean-scan.json"
```

只有在清理过程中没有 `indeterminate` 目标、预期备份存在、CLI 全范围终检成功，并且独立清理后复扫没有发现剩余特征时，才能称活动场景范围为干净。

## 安全契约

权威流程由 [Agent Skill](skills/maya-umbrella-batch-antivirus/SKILL.md) 及其 [操作契约](skills/maya-umbrella-batch-antivirus/references/operation-contract.md) 定义。核心保证如下：

- 批准绑定扫描器路径、目标集合、报告字节、感染路径和源哈希；Maya 年份是额外的明确清理参数与批准事项。
- `_virus` 是固定的备份/隔离目录。不要设置 `MAYA_UMBRELLA_IGNORE_BACKUP=true`，也不要自定义 `MAYA_UMBRELLA_BACKUP_FOLDER_NAME`。
- 特征扫描固定排除 `_virus`，其中可能保留感染场景的原始字节。必须妥善保留并隔离这些备份；活动场景结果干净不代表备份目录干净。
- 已有同名备份绝不会被覆盖。只有获得批准才能保留或迁移它们，之后必须重新扫描。
- 清理会预建空的 `Maya.env`，使用隔离的临时 `MAYA_APP_DIR`，并禁用 Python user-site。
- 现有 `Maya.env`、`userSetup.py`、`userSetup.mel`、`.pth`、`sitecustomize.py`、模块路径、插件路径和自定义脚本路径不会被执行或删除。
- 感染的引用文件或批准场景清单外的 Maya/Python 文件会让清理在场景修改前中止；它们需要独立范围与批准。
- `indeterminate` 是失败状态，绝不能当作干净结果。仅有成功的清理退出码不足以完成验证。

## 兼容性与限制

- 便携式发布包面向 Windows x64。
- 扫描模式不需要 Maya；清理需要本机安装的、本次运行明确选择年份的 Maya。
- Maya 2019–2021 使用 Python 2，当前引擎无法安全保存非 ASCII 场景路径。CLI 会在备份或启动 Maya 前拒绝该组合。
- 路径失败后，不得通过移动、重命名或复制场景来绕过批准约束。选择另一个 Maya 年份必须重新扫描并批准。
- 通过较新 Maya 版本保存可能改变场景兼容性。
- 扫描器检测固定引擎支持的已知特征，不提供通用恶意代码分析保证。

## Agent Plugin 与 Skill 分发

仓库遵循 [Agent Plugins 1.0](https://agent-plugins.org/specification)。[`plugin.json`](plugin.json) 是包清单，兼容客户端通过固定的 `skills/` 布局发现独立的 [`skills/maya-umbrella-batch-antivirus/SKILL.md`](skills/maya-umbrella-batch-antivirus/SKILL.md) 入口。Agent Plugins 规范定义包结构，不规定必须使用某种安装或发布服务。

### ClawHub

ClawHub 分发 Skill 目录，而不是只含根清单的包。维护者可以使用固定版本的 dry-run 验证待发布内容：

```powershell
npx --yes clawhub@0.23.3 skill publish .\skills\maya-umbrella-batch-antivirus `
  --owner loonghao `
  --categories security,operations `
  --topics maya,antivirus,malware,virus-scan,scene-cleanup `
  --dry-run `
  --json
```

获得发布授权后，先运行 `npx --yes clawhub@0.23.3 login`。仓库配置 `CLAWHUB_TOKEN` secret 后，每个正式（非 prerelease）GitHub Release 都会触发 `ClawHub Skill` 工作流；`workflow_dispatch` 仅允许从 `main` 进行受控首发或恢复发布。工作流固定使用 ClawHub CLI 0.23.3 并保存结构化回执。`pending-publication` 或 `submitted` 表示 registry 工作流已接受或记录提交，但尚未验证公开可见。

确认公开版本可见后，使用以下命令安装：

```powershell
openclaw skills install @loonghao/maya-umbrella-batch-antivirus
# 或使用 ClawHub registry CLI
npx --yes clawhub@0.23.3 install @loonghao/maya-umbrella-batch-antivirus
```

## 常见问题

### 支持 Agent Skills 的 Codex 或 WorkBuddy 能扫描并受控清理 Maya 场景病毒吗？

可以，前提是所选客户端版本支持 Agent Skills，并且能够访问 Windows CLI。安装 `maya-umbrella-batch-antivirus` 后，让它扫描一个精确目录即可。受控清理仍必须在扫描后披露命中并取得明确批准。仓库验证了 Skill 发现能力和边界明确的操作流程，但不声称已对每个 Agent 客户端版本完成端到端验证。

### 扫描会修改 Maya 文件吗？

不会。扫描模式不会启动 Maya 或改写场景，但可能写入临时输出和用户要求的 JSON 报告。清理是独立且需要批准的操作，只会在建立经过验证的备份后强制保存修复场景。

### 是否需要 Python 或 Autodesk Maya？

便携式发布包内嵌 Python 运行时，因此扫描和清理都不需要系统 Python。扫描不需要 Maya；清理需要明确选择的 Autodesk Maya 年份，因为修复要通过该安装的 `mayapy.exe` 和 Maya API 执行。

### 它会清理 `userSetup.py` 或整个 Maya 安装吗？

不会。只读发现可以报告匹配的外部 Maya/Python 文件，但该流程不会删除它们。场景扫描结果干净，不能证明启动目录、Maya 安装、感染的引用文件或其他外部文件没有问题。

### Maya Umbrella Scanner 是通用杀毒软件吗？

不是。它是范围限定在 `.ma` 和 `.mb` 文件的 Maya 场景病毒扫描器。请继续使用终端防护和更全面的 Maya 安全措施。

## 发布与架构

Release Please 统一维护版本与变更日志。它同步 `pyproject.toml`、`maya_umbrella_scanner/__version__.py`、`plugin.json` 和发布 manifest，再创建 `vX.Y.Z` 标签与 GitHub Release。标签工作流使用固定构建工具生成 Windows 便携 ZIP 与 `SHA256SUMS`。

重跑不会覆盖已有 Release 资产。若上一次只上传了 ZIP，重跑可以为这些精确字节补传校验文件；已有 ZIP 与校验文件不一致时会失败关闭。

运行时架构以及没有立即全面改写 Rust 的原因见 [ADR 0001](docs/adr/0001-portable-cli-runtime.md)。

## 许可证

Maya Umbrella Scanner 使用 [MIT License](LICENSE)。
