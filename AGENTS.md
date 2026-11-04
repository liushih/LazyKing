# 给 AI 编码助手的说明

适用于 Claude Code、Codex、Cursor 等所有在本仓库工作的 AI 工具。规则的完整说明在 [CONTRIBUTING.md](CONTRIBUTING.md)，这里只列必须记住的几条。

- **先读 `CONTRIBUTING.md`**：本仓库是通用工具，哪些内容能进 git、哪些属于项目衍生物不能进，那里写得很清楚。
- **改了运行行为就自动升版本号**，与功能放在同一个提交里，不要等使用者提醒。用 `scripts/bump_version.py`，不要手改清单。判断标准、版本号怎么选、提交前要跑哪些检查，见 `CONTRIBUTING.md` 的「升版本是提交的一部分」。
- **提交后询问是否推送**，使用者没有要求时不要自行推送。
- 跑全部测试：`.venv/Scripts/python.exe -m pytest tests -q`。
