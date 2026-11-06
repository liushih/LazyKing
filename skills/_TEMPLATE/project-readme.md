# <PROJECT_ID> data-tools（仅本机）

本目录由 LazyKing 同步生成，只在本机使用，不能提交进业务仓库。同步工具会把
`data-tools/`、`.data-tools/` 和生成出来的技能入口整体写进业务仓库 `.gitignore`。

## 首次接入

1. 确认本机有 Python 3.11+（没有则到 https://www.python.org/downloads/ 下载安装，勾选 Add to PATH）。
2. 在业务仓库根目录运行 `powershell -ExecutionPolicy Bypass -File data-tools/bootstrap.ps1`。
3. 打开 AI 工具，说「初始化个人配置」，按提示生成 `personal.yaml` 和 `.env`。
   没有 `.env` 时先复制 `.env.example` 为 `.env`；团队共用的地址和端口已写在里面，只需填自己的账号密码。
4. `data-tools/`、`.data-tools/`、生成的技能入口都不提交；`personal.yaml` 与 `.env` 只留在本机。
5. 说「造 100 张 <业务对象>」开始使用。

## 业务模块

复杂业务的脚本在 `.data-tools/projects/<PROJECT_ID>/scripts/`，只在本机使用。
需要团队共享时，通过公司内网制品库或共享目录分发，不要提交进业务仓库 git，也不要用
`git add -f` 绕过忽略规则。凭据只放本机 `.env`。

## 团队协作

业务仓库只保留业务代码。团队共享的 adapter、坑库、脚本和模板由团队约定的内网渠道分发，
每人放到自己的 `.data-tools/`。不要把这些内容提交进业务仓库。

## 更新

`powershell -ExecutionPolicy Bypass -File data-tools/update.ps1`

更新只刷新本机副本；不需要提交任何 data-tools 变更。
