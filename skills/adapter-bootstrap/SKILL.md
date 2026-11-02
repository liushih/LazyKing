---
name: adapter-bootstrap
description: >-
  接入新的业务流程，边跑边记生成或更新本地适配层。用户说「接入」「新业务」
  「第一次造 X」「打通这个流程」时使用。产出 adapter.yaml 与 pitfalls.md。
---

# 适配层接入

## 适用场景

- 新业务首次造数
- 现有业务新增步骤，或修正已知失败原因

## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；再找不到读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet：有新版本就把提示原样告诉用户，不自动更新；脚本不存在、无新版本或检查失败则继续。

## 前置检查

1. 确认项目 ID 与数据目录（默认使用第 0 步解析的 <DATA_HOME>）
2. 收集：接口地址、认证方式、目标状态
3. 逐项确认：字段映射、枚举取值、异步时序
4. 读 `<TOOLS_DIR>/skills/_references/adapter-contract.md` 与 `pitfalls.md`

## 路径

命令里的 `<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`：从当前目录向上查找；找不到再读 `DATA_TOOLS_DIR`，再找不到读 `~/.data-tools/config.yaml` 的 `tools_dir`；仍找不到就问用户业务仓库根目录，不要猜。`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`：先读 `DATA_TOOLS_HOME`，没有再从当前目录向上查找，最后回退 `~/.data-tools`。

解释器优先 `<TOOLS_DIR>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（POSIX）；没有 venv 时用 `py -3.11` / `py -3` / `python` / `python3`，要求 3.11+；有 Python 但没 venv 时运行 `<TOOLS_DIR>/bootstrap.ps1`。

## 执行

1. 从 `<TOOLS_DIR>/skills/_TEMPLATE/adapter.example.yaml` 起草 `<数据目录>/projects/<项目ID>/adapter.yaml`
2. 先跑 1 条：`"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/run.py" --project <项目ID> --entity <业务对象> --count 1`
3. 失败就查接口或问用户，不猜字段
4. 跑通后补 `verify` 段，格式见 `<TOOLS_DIR>/skills/_TEMPLATE/adapter.example.yaml`
5. 每条坑按四段（现象 / 原因 / 绕法 / 适用）追加到 `pitfalls.md`；追加前先读现有条目，按「现象」去重
6. 用同一批次号重跑，确认幂等
7. 接入完成后同步维护项目 `.env.example` 的键名，不写值

## 失败处理

| 情况 | 动作 |
|---|---|
| 接口返回结构未知 | 打印响应前 500 字符，不猜字段 |
| 枚举取值不明 | 走匹配接口或询问，不硬编码 |
| 连续失败 3 次 | 停下，列出已确认与未确认项 |
| 用户无法提供凭据 | 保留适配层，标记 `.env` 待填 |
