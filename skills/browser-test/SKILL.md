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

1. 读 `<DATA_HOME>/projects/<项目ID>/browser/browser.yaml`。
2. 没有就按 `<TOOLS_DIR>/skills/_TEMPLATE/browser.example.yaml` 建档，确认前端根地址和登录方式；凭据只写 `${VAR}`。
3. 读同目录 `browser/pitfalls.md`，先看已有坑。
4. 确认目标环境；用户未说明时问一次。

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

环境不完整时先跑：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" doctor --project <项目ID>
```

## 失败处理

| 情况 | 动作 |
|---|---|
| 退出码 2 | 配置错误：按提示补 `browser.yaml`、流程文件或变量，不启动浏览器 |
| 退出码 3 | 流程不存在：`list` 看可选项，或先 `probe` 建流程 |
| 退出码 4 | 环境错误：按提示检查 Chrome、Playwright、profile 占用或登录 |
| 退出码 1 | 流程失败：读诊断包 `diagnosis.md`，改流程后重跑 |
| 出现新坑 | 按四段（现象 / 原因 / 绕法 / 适用）追加到 `browser/pitfalls.md`，按「现象」去重 |

自愈顺序：读诊断 → 判断是选择器、等待信号、接口还是前置条件 → 改 YAML（复杂交互抽到项目 `scripts/` 的 `impl`）→ 重跑。只以退出码 0 报通过；未通过时明确说失败步骤。

诊断包细节见 `<TOOLS_DIR>/skills/_references/browser-diagnosis.md`。

## 铁律

- 先查流程和坑库，不重复探索。
- 不写固定 sleep；等接口、URL、元素或文本。
- 选择器必须唯一，优先 `data-testid`，其次角色/精确文本；多命中要收窄范围。
- 一条流程一次连接，不在步骤间重开浏览器。
- 业务逻辑只进项目 `scripts/`，不进 `runtime/`。

## 记忆规则

- 提交：`browser/browser.yaml`、`browser/flows/*.yaml`、`browser/pitfalls.md`、项目 `scripts/` 的 impl。
- 不提交：`.data-tools/browser/` 下的 profile、截图、报告、诊断包。
- 凭据只放项目 `.env`；新增键时同步更新 `.env.example`。
- 稳定后再删旧脚本或旧技能，避免知识丢失。
