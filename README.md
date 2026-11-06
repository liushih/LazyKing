# claudeTool

用白话让 AI 帮你连库、造数、测页面、写报告、管代码托管。支持 Claude Code、Cursor、Codex、DeepSeek Harness。

个人/全局模式下，业务规则存在本机适配层，凭据只存本机，都不进仓库；团队项目模式下工具和适配层也只在本机，不进入业务仓库 git，凭据仍只存本机。

## 能做什么

| 你说 | 它做 |
| --- | --- |
| 查一下 dev 库最近 3 条提货单 | 连库执行 SQL，返回结果 |
| 把这个 SQL 文件跑一下 | 读取文件执行，支持多语句 |
| 在 dev 造 100 张提货单，跑到 UPLOADED | 并发造数，逐单记台账 |
| 同一批次重跑，把失败的补上 | 跳过已完成，只补失败 |
| 测一下 B2D 待发货 | 打开 Chrome 复跑已沉淀流程，失败出诊断包 |
| 写这周的周报，顺便出 Word | 采集提交与禅道任务，生成并渲染 |
| 把这个改动提交并推到 dev | 检查提交规范，回显后推送 |
| 发版我这个需求的模块到 dev | 按改动推断模块，确认后触发 Jenkins 构建 |
| 接入 XX 新业务 | 陪你跑通，生成该业务的规则和坑库 |

## 快速开始

需要 Windows、Python 3.11+、Git。

**1. 初始化**

```powershell
git clone https://github.com/liushih/claudeTool.git C:\project\claudeTool
cd C:\project\claudeTool
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

建虚拟环境、装依赖，并记录工具目录。

**2. 装进 AI 工具**

Claude Code：

```text
/plugin marketplace add liushih/claudeTool
/plugin install data-tools@data-tools
```

装完重启一次应用。

Cursor / Codex：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target cursor,codex -Scope project -ProjectDir C:\你的业务仓库
```

DSH（DeepSeek Harness）：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target dsh -Scope global
```

技能写到 `%USERPROFILE%\.dsh\skills\`，新开会话即生效（不用重启），输入 `/db-access` 可直接调用，也能按描述自动触发。换成 `-Scope project -ProjectDir C:\你的业务仓库` 则只在该仓库生效。

项目内生成的入口（`.cursor/rules/`、`.dsh/skills/`、`AGENTS.md` 里的块）只在本机使用，不要提交进业务仓库。团队接入请用下面的 `sync_project.py`，它会把生成的技能目录写进 `.gitignore`；Codex 只能写 `AGENTS.md`，无法局部忽略，团队模式不支持。

**3. 接入第一个业务**

新开会话，直接说：

```text
接入 B2D 提货单业务
```

按提示给接口地址、账号即可。接入完成后就能直接说「造 100 张提货单」。

> 个人/全局插件方式只分发规则，不带 Python 依赖，所以仓库必须 clone 到本机并跑过 `setup.ps1`。

## 团队项目接入（本地安装，不进业务仓库 git）

维护者在 claudeTool 仓库执行：

```bash
python scripts/sync_project.py --project-dir C:\project\<业务仓库> --project-id <项目ID> --targets claude
```

业务仓库本地会出现 `data-tools/`、`.claude/skills/`、`.data-tools/`，但同步工具会把它们整体写进 `.gitignore`，**不会进入业务仓库 git**。业务仓库只保留业务代码。`--targets` 可选 `claude,cursor,dsh`；codex 只能写 `AGENTS.md`，无法局部忽略，因此团队模式不生成。

同事接入时，由团队维护者通过内网制品库或共享盘分发 `data-tools/`（或各自从内网镜像同步），放到业务仓库根目录后：

1. 跑 `data-tools/bootstrap.ps1`（没有 Python 会提示下载）
2. 打开 AI 工具，说「初始化个人配置」，按 `project-setup` 的提示生成 `personal.yaml` 和 `.env`。没有 `.env` 时先复制 `.env.example` 为 `.env`，团队共用的地址和端口已经写好，只需填自己的账号密码
3. 直接说「造 100 张提货单」

复杂业务的 impl 模块（如登录客户端、链路封装）也放 `.data-tools/projects/<项目ID>/scripts/`，只在本机使用；团队共享通过内网渠道分发，不要提交进业务仓库。B2D/B2C 已内置，不再依赖旧 `hexin-data-gen`/`hexin-db-tools`。

更新：`data-tools/update.ps1`，会刷新本机的 `data-tools/`、生成的技能入口和 `.gitignore`；发现新版本时技能会先询问是否更新。个人全局使用仍可用插件市场，互不影响。

要用浏览器测试，还需要给项目配前端地址和登录方式，步骤见 [使用说明：浏览器测试](docs/usage.md#十三浏览器测试)。本机需要装 Chrome。

## 八个技能

| 技能 | 触发词 |
| --- | --- |
| `adapter-bootstrap` 接入业务 | 接入、新业务、第一次、打通 |
| `data-gen-core` 批量造数 | 造 N 条、批量、压测数据、补数据 |
| `db-access` 查改库 | 查一下、连 dev 库、改成、看 redis / mongo |
| `browser-test` 浏览器测试 | 测一下、走一遍、浏览器验证、复现、回归 |
| `report-writer` 写报告 | 日报、周报、月报、述职 |
| `git-workflow` 代码托管 | 提交、推送、建 MR、开分支、同步热修 |
| `jenkins-deploy` Jenkins 发版 | 发版、构建、部署、Jenkins |
| `project-setup` 个人配置 | 初始化个人配置、新同事接入、配置我的账号 |

## 配置

通常不用改。需要时用环境变量覆盖：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_TOOLS_DIR` | `~/.data-tools/config.yaml` 的 `tools_dir` | 工具目录 |
| `DATA_TOOLS_HOME` | 项目内 `.data-tools/`，没有则 `%USERPROFILE%\.data-tools` | 适配层、台账、坑库、凭据；设置后优先使用 |

解析顺序：`DATA_TOOLS_HOME` > 从当前目录向上找到的 `.data-tools/` > `%USERPROFILE%\.data-tools`。所以在业务仓库里默认落在仓库自己的 `.data-tools/`（只在本机，不提交），个人全局使用回退到用户目录。

每个项目一份独立目录：`<DATA_HOME>\projects\<项目ID>\`，里面是 `adapter.yaml`、`.env`、`pitfalls.md`、`scripts/` 等。

DSH 的沙箱只允许写工作区和临时目录。个人/全局模式下 `<DATA_HOME>` 是 `~/.data-tools`，造数、接入要写台账和适配层时，把 `DATA_TOOLS_HOME` 指到工作区内（例如 `<仓库>/.data-tools`），或让该会话使用完全访问权限。团队模式的数据目录本来就在业务仓库内，不受影响。只读查库不受影响。

## 文档

- [使用说明](docs/usage.md)：适配层写法、造数参数、数据库、浏览器测试、报告、代码托管、常见问题
- [设计文档](docs/superpowers/specs/) · [实现计划](docs/superpowers/plans/)
- [贡献指南](CONTRIBUTING.md)

## 开发

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/check_secrets.py
```

| 目录 | 用途 |
| --- | --- |
| `skills/` | 技能规则、契约文档、模板 |
| `runtime/` | 执行引擎 |
| `scripts/` | 命令行入口 |
| `hexin-*` | 旧工具，用法见各自目录 |

提交前先读 [CONTRIBUTING.md](CONTRIBUTING.md)：只有通用能力进 git，项目衍生物不进。

## License

MIT，见 [LICENSE](LICENSE)。
