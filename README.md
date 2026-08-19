# maya_umbrella_scanner
A portable version for maya umbrella scanner.

# 安装
从 [release](https://github.com/loonghao/maya_umbrella_scanner/releases) 页面下载安装包，然后解压缩并使用。

# 用法
## 病毒扫描
使用 --path 参数指定要扫描的路径，程序将递归扫描路径下所有的 ma 或 mb 文件。
```shell
maya_umbrella --path <your/search/path>
```
例如，要扫描 c:/test 文件夹下的所有 ma 或 mb 文件。命中时，程序会输出本次生成的临时感染清单路径。
```shell
maya_umbrella --path c:/test
```
## 自动杀毒
使用 --path 参数指定要扫描的路径，程序将递归扫描路径下所有的 ma 或 mb 文件。
使用 --maya-version 参数指定本地安装的 Maya 版本，例如 2019。需要启动本地安装的 Maya 的 standalone 版本进行杀毒。

新版清理不再接受没有批准证据的直接 `--maya-version` 调用。请先安装下方 Agent Skill，使用它的 `scan --report` 生成命中清单和 `report_file_sha256`，经用户明确批准后再执行 `clean`。这也适用于人工 CLI 操作。

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

Agent 执行清理前必须确认 `maya_umbrella --help` 包含 `--approved-scan-report`。当前公开的 v0.1.8 可用于受控扫描，但不具备这项清理门禁；请使用合并本变更后发布的 scanner。Skill 会让旧版清理命令在任何 Maya 场景被修改前失败关闭。每次 `--report` 都应使用一个尚不存在的 `.json` 路径，以保留独立审计证据；scan 在 stdout 输出的 `report_file_sha256` 必须与命中清单一起交给用户批准，并原样传给 clean。

为避免把任意现有项目子树从扫描范围隐藏，备份/隔离目录固定为 `_virus`。自定义 `MAYA_UMBRELLA_BACKUP_FOLDER_NAME` 现会失败关闭；这是新版的安全性 breaking change。

清理进程会预建空的 `Maya.env`，使用临时隔离的 `MAYA_APP_DIR`，并禁用 Python user-site；不会执行用户现有的 `Maya.env`、`userSetup.py`、`userSetup.mel`、`.pth`/`sitecustomize.py` 或自定义启动路径。只读检查可以报告相关 Maya/Python 目录中的匹配文件，但不会删除它们；这类文件需要另行批准检查和隔离，不能从场景复扫结果推断为安全。

### ClawHub

ClawHub 分发的是 Skill 子目录，不是仅含根 `plugin.json` 的完整 Agent Plugins 包。发布前先做 dry-run：

```powershell
npx --yes clawhub@0.23.3 skill publish .\skills\maya-umbrella-batch-antivirus `
  --owner loonghao `
  --dry-run `
  --json
```

正式发布前先执行 `npx --yes clawhub@0.23.3 login`；随后从上述命令移除 `--dry-run`，或在 GitHub Actions 手动运行 `ClawHub Skill` workflow（需要仓库 secret `CLAWHUB_TOKEN`）。公开版本通过安全审核并可见后，可通过 CLI 安装：

```powershell
openclaw skills install @loonghao/maya-umbrella-batch-antivirus
# 或使用 ClawHub registry CLI
npx --yes clawhub@0.23.3 install @loonghao/maya-umbrella-batch-antivirus
```
