# 浏览器诊断与自愈

流程失败时，`browser.py run` 会生成诊断包，路径打印在输出里；也可以运行 `browser.py diagnose --project <项目ID>` 重看最近一份。

## 诊断包内容

位于 `.data-tools/browser/artifacts/<流程名>-<时间戳>/`：

| 文件 | 内容 |
|---|---|
| `diagnosis.md` | 失败步骤、期望/实际、当前 URL、页面标题、步骤耗时、建议动作 |
| `failure.png` | 失败瞬间截图（截图失败时可能缺失） |
| `page.html` | 当前 DOM |
| `requests.json` | 最近请求，Cookie / Authorization / Set-Cookie 已脱敏 |
| `console.log` | 前端报错与告警 |
| `flow.snapshot.yaml` | 本次执行的流程副本 |
| `run.log` | 每步状态与耗时 |
| `trace.zip` | 加 `--trace` 时生成 |

## 自愈顺序

```text
run 失败
→ 读 diagnosis.md 和产物
→ 判断属于哪类：
   选择器变化 / 等待信号不对 / 接口路径变化 / 前置条件缺失 / 登录失效
→ 修改 flow YAML；复杂交互抽到 impl
→ 重跑，直到退出码 0
→ 出现新坑追加到 browser/pitfalls.md
→ 只以退出码 0 报通过
```

判断提示：

- `diagnosis.md` 里「命中 N 个」→ 选择器太宽，收窄到 `data-testid`、行内 `in` 或精确文本。
- `wait_response` 超时 → 打开 `requests.json` 看实际接口路径和状态码。
- `wait_visible` 超时 → 看 `page.html` 和截图，确认元素是否更换了容器或 testid。
- 登录失败 → 确认 `success.url_path` 只比 pathname，且 profile 未被其他 Chrome 占用。
- 页面跳到了预期外的 URL → 先补前置条件或等待信号，不要加固定 sleep。

## 坑库格式

`browser/pitfalls.md` 沿用四段式：

```markdown
## P1 侧边栏也有「查询」按钮

- 现象：点击查询后列表没刷新，实际点到了侧边栏
- 原因：文本选择器同时命中侧边栏和页面按钮
- 绕法：用 `{testid: ...}` 或 `{in: row, ...}` 限定范围
- 适用：所有带同名侧边栏按钮的页面
```

追加前按「现象」去重；同一现象更新绕法，不新增重复条目。

## 记忆边界

- 提交：`browser.yaml`、`flows/*.yaml`、`pitfalls.md`、项目 `scripts/` 的 impl。
- 不提交：`.data-tools/browser/` 下的 profile、截图、报告、诊断包、probe 快照。
- 凭据只放项目 `.env`。
