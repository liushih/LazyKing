---
name: data-gen-core
description: >-
  按项目业务流程批量生成合规测试数据。用户说「造 N 条/张 <业务对象>」
  「批量生成测试数据」「压测数据」「补数据」时使用。执行前必须读取本地适配层；
  没有适配层时必须转 adapter-bootstrap，不允许现场推导。
---

# 批量造数

## 适用场景

- 造数：造、生成、批量、压测数据、补数据
- 用户给出业务对象与数量，例如「造 100 张提货单」

不适用：

- 新业务首次接入 → 先用 `adapter-bootstrap`
- 只查询、不产生数据 → 用 `db-access`

## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：从当前目录向上查找 .data-tools/；找不到读 DATA_TOOLS_HOME；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet：有新版本就把提示原样告诉用户，不自动更新；脚本不存在、无新版本或检查失败则继续。

## 前置检查

1. 读 `<数据目录>/projects/<项目ID>/adapter.yaml`
2. `entities` 中存在对应业务对象
3. 同目录 `.env` 含 `envs.dev` 引用的全部变量
4. 读同目录 `pitfalls.md`，记下与本业务对象相关的坑
5. 确认目标环境；用户未说明时问一次

任一项缺失就停止执行并说明缺什么。
**没有适配层时必须转 `adapter-bootstrap`，不允许现场推导。**

## 路径

命令里的 `<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`：从当前目录向上查找；找不到再读 `DATA_TOOLS_DIR`；仍找不到就问用户业务仓库根目录，不要猜。`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`：同样向上查找，找不到再读 `DATA_TOOLS_HOME`，最后回退 `~/.data-tools`。

解释器优先 `<TOOLS_DIR>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（POSIX）；没有 venv 时用 `py -3.11` / `py -3` / `python` / `python3`，要求 3.11+；有 Python 但没 venv 时运行 `<TOOLS_DIR>/bootstrap.ps1`。

规则细节按需读取：`<TOOLS_DIR>/skills/_references/adapter-contract.md`（字段与步骤写法）、`runtime-contract.md`（占位符、重试、verify）。

## 执行

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/run.py" --project <项目ID> --entity <业务对象> --count <数量> --workers 5 [--run-id <批次号>] [--env dev]
```

- 台账：`<数据目录>/projects/<项目ID>/ledger.csv`
- 断点续跑：同一 `--run-id` 重跑会跳过已完成
- 验证：适配层 `verify` 段由 `run.py` 自动执行，未通过计入 failed

## 失败处理

| 情况 | 动作 |
|---|---|
| 无 `adapter.yaml` | 停，转 `adapter-bootstrap` |
| 业务对象不存在 | 列出可选项并询问 |
| `.env` 缺键 | 报键名，引导录入 |
| 认证失败 | 指向凭据位置，不盲目重试 |
| 业务接口报错 | **先查 `pitfalls.md`** 有无同现象；命中就按绕法走，不重新试错 |
| 网络超时 | 写请求不自动重试；读请求重试 2 次，仍失败则停 |
| 批量部分失败 | 报告 done / failed，给续跑命令，不报成功 |
| 出现新坑 | 按四段（现象 / 原因 / 绕法 / 适用）追加到 `pitfalls.md`，追加前按「现象」去重 |
