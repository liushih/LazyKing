---
name: browser-test
description: >-
  用可见 Chrome 执行可复跑的页面测试与联调。用户说「测一下 X」「走一遍 X 流程」
  「浏览器验证」「点一遍」「复现一下」「回归」时使用。先查已沉淀流程，
  没有才探索；失败生成诊断包，按诊断修流程。
---

# 浏览器测试

用本机 Chrome 打开前端页面，按流程操作并断言结果。目标是「下次不用重新想」：入口、选择器、等待信号、断言和踩过的坑都写在项目 `browser/` 下。

## 适用场景

- 改完前端或接口，在页面上确认功能正常
- 复现 Bug，按真实操作路径走一遍
- 新流程首次联调，需要把步骤沉淀下来
- 回归已有页面流程

不适用：只查数据 → `db-access`；批量造数 → `data-gen-core`；定位后端根因 → 排查类技能。

## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；再找不到读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet。若提示有新版本：问用户「发现新版本，是否现在更新？」；用户确认后运行 <TOOLS_DIR>/update.ps1，完成后提醒用户检查 git status 并提交 data-tools/、生成的技能入口和 .gitignore；用户拒绝则继续，本次会话不再追问。脚本不存在、无新版本、检查失败或 update_check 关闭时继续。

## 前置检查

0. 运行 `"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/config.py" --project <项目ID> check --capability browser`。有缺失时用 `project-setup` 补齐；不现场猜个人值，不修改共享 yaml；密钥只提示用户在自己的终端运行 `set-secret`。

1. 读 `<DATA_HOME>/projects/<项目ID>/browser/browser.yaml`。
2. 没有就按 `<TOOLS_DIR>/skills/_TEMPLATE/browser.example.yaml` 建档，确认前端根地址和登录方式；凭据只写 `${VAR}`。
3. 读同目录 `browser/controls.md`。命中本次要操作的控件时，沿用记录里的页面和失败现象，不重新扫描页面猜操作。
4. 读同目录 `browser/pitfalls.md`，先看已有坑。
5. 确认目标环境；用户未说明时问一次。

## 执行

先看已有流程：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" list --project <项目ID>
```

命中就直接跑：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" run --project <项目ID> --flow <流程名> --env dev --var 名称=值
```

没有对应流程时，先探索：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" probe --project <项目ID> --url <页面地址>
```

按 `<TOOLS_DIR>/skills/_references/browser-flow-contract.md` 把入口、步骤、等待信号、断言写成 `browser/flows/<流程名>.yaml`，再 `run` 到通过。

常用选项（完整表见 `browser-flow-contract.md` 第 10 节）：`--headed` 本次显示窗口（默认不显示，见下）；`--profile <路径>` 换浏览器 profile，用于绕开被占用的 profile 或强制重新登录；`--trace` 录制 trace；`--json` 机器可读输出。常驻和无头的视口固定 1280x720，`--headed` 是最大化，两者页面尺寸不同，对比失败时用同一种模式。

**浏览器默认在后台常驻**：测试连的是工具自己开的专用无头 Chrome，不弹窗，不碰用户日常的 Chrome。第一次 `run` 自动拉起，之后每次只连接、跑完断开，不要在每次测试前后手动开关浏览器。用户要看页面才加 `--headed`；不用时 `browser.py stop --project <项目ID>` 关掉（`--all` 关本机全部）。

**运行产物会自动清理**：报告保留最近 20 份，诊断包和探索快照各保留 10 份且最多 7 天，`--trace` 录制的 trace 只在失败时随诊断包保留。每次 `run` / `probe` 开始时会清理旧产物；流程通过时会立即删掉该流程之前的失败诊断包。测试任务收尾、不再需要诊断时，运行 `clean` 清空全部诊断包、探索快照和 trace：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" clean --project <项目ID>
```

`clean` 会同时删除该 profile 里 Chrome 可重建的缓存（`Cache`、`Code Cache` 等，可能占几百 MB），Cookies 和 Local Storage 保留，登录态不受影响；`clean --all` 清理本机所有 profile。临时截图、页面 HTML 一律写到 `.data-tools/browser/probes/` 或系统临时目录，由上面的规则统一清掉，不要写进业务仓库或 `.data-tools/browser/` 根目录。

环境不完整时先跑：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" doctor --project <项目ID>
```

## 失败处理

| 情况 | 动作 |
|---|---|
| 退出码 2 | 配置错误：按提示补 `browser.yaml`、流程文件或变量，不启动浏览器 |
| 退出码 3 | 流程不存在：`list` 看可选项，或先 `probe` 建流程 |
| 退出码 4 | 环境错误：按提示检查 Chrome、Playwright、profile 占用或登录。提示「测试浏览器被关闭」是浏览器在运行中被手动关了，结果无效，直接重跑，不要去改流程 |
| 退出码 1 | 流程失败：读诊断包 `diagnosis.md`，改流程后重跑 |
| 出现新坑 | 按四段（现象 / 原因 / 绕法 / 适用）追加到 `browser/pitfalls.md`，按「现象」去重 |

原来能通过、突然稳定失败时，先查被测前端有没有刚发布（`curl -I <前端地址>` 看 `Last-Modified`），再手工点一次对应功能，确认功能本身变了再改流程；不要先改选择器或加等待。

自愈顺序：读诊断 → 判断是选择器、等待信号、接口还是前置条件 → 改 YAML（复杂交互抽到项目 `scripts/` 的 `impl`）→ 重跑。只以退出码 0 报通过；未通过时明确说失败步骤。

诊断包细节见 `<TOOLS_DIR>/skills/_references/browser-diagnosis.md`。

## 铁律

- 先查流程、`browser/controls.md` 和坑库，不重复探索。
- 不写固定 sleep；等接口、URL、元素或文本。
- 选择器必须唯一，优先 `data-testid`，其次角色/精确文本；多命中要收窄范围。
- 一条流程一次连接，不在步骤间重开浏览器；也不要在两次测试之间关浏览器，它是常驻的。
- 业务逻辑只进项目 `scripts/`，不进 `runtime/`。

## 记忆规则

- 写完或改完团队共享文件后立刻暂存，不要询问。仅当文件在业务仓库内时运行；个人目录 `~/.data-tools` 不运行：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/track_shared.py" --project-dir <业务仓库根> <刚写或刚改的文件>
```

  多个文件跟在同一条命令后面。可暂存：`browser/browser.yaml`、`browser/flows/*.yaml`、`browser/controls.md`、`browser/pitfalls.md`、项目 `scripts/` 的 impl，以及同目录其他团队共享文件。
- 不暂存：`.data-tools/browser/` 下的 profile、截图、报告、诊断包，以及 `.env`、`personal.yaml`、台账、token。这些路径脚本会拒绝，不要加 `-f`。
- 暂存不是提交。提交和推送仍按 `git-workflow`，推送前必须等用户确认。
- 凭据只放项目 `.env`；个人非敏感值放 `personal.yaml`；新增键时按是否密钥更新 `.env.example` 或 `personal.example.yaml`。
- 稳定后再删旧脚本或旧技能，避免知识丢失。
