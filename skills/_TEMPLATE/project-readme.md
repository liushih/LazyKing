# <PROJECT_ID> data-tools

本目录由 claudeTool 同步生成，不要手改。

## 首次接入

1. 确认本机有 Python 3.11+（没有则到 https://www.python.org/downloads/ 下载安装，勾选 Add to PATH）。
2. 在业务仓库根目录运行 `powershell -ExecutionPolicy Bypass -File data-tools/bootstrap.ps1`。
3. 复制 `.data-tools/projects/<PROJECT_ID>/.env.example` 为 `.env`，填入账号。
4. 打开 AI 工具，直接说「造 100 张 <业务对象>」。

## 业务模块

复杂业务的脚本在 `.data-tools/projects/<PROJECT_ID>/scripts/`，随仓库提交；
不需要旧 claudeTool、hexin-data-gen 或 hexin-db-tools。凭据只放本机 `.env`。

## 更新

`powershell -ExecutionPolicy Bypass -File data-tools/update.ps1`

更新会刷新 `data-tools/`、技能入口和 `.gitignore`；更新后按提示提交这些变更。
