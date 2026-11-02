# <PROJECT_ID> data-tools

本目录由 claudeTool 同步生成，不要手改。

## 首次接入

1. 确认本机有 Python 3.11+（没有则到 https://www.python.org/downloads/ 下载安装，勾选 Add to PATH）。
2. 在业务仓库根目录运行 `powershell -ExecutionPolicy Bypass -File data-tools/bootstrap.ps1`。
3. 复制 `.data-tools/projects/<PROJECT_ID>/.env.example` 为 `.env`，填入账号。
4. 打开 AI 工具，直接说「造 100 张 <业务对象>」。

## 更新

`powershell -ExecutionPolicy Bypass -File data-tools/update.ps1`
