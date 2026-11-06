# 浏览器显示检查设计

**日期**：2026-11-06
**状态**：待审阅
**关联**：`runtime/browser/`、`skills/browser-test/`、`skills/_references/browser-flow-contract.md`、`skills/_TEMPLATE/browser-flow.example.yaml`、`docs/usage.md`

## 1. 背景与目标

`browser-test` 目前的断言只覆盖功能信号：元素可见、文本、URL、元素数量、接口状态。流程通过后，测试仍反馈过两类问题：

- 详情页/列表页有字段没有显示出来（整块漏渲染，或标签在、值为空）。
- 列宽或容器宽度不足，内容被省略号截断，看不到全文。

这两类问题没有任何断言覆盖，只能靠人工发现，导致自动化测试通过但移交测试后仍被退回。

目标是给步骤增加显示检查断言，让流程在核对功能的同时，核对该页面/弹窗的字段完整性，并扫描容器内的截断与溢出，把问题拦在测试移交之前。

成功标准：

- 声明了显示检查的页面，字段缺失、值为空、内容被裁切时流程失败（退出码 1），诊断包能定位到具体字段或元素。
- 未声明显示检查的流程行为不变。
- 异步渲染的字段晚出现时不误报（轮询等待）。
- 不引入截图基线，不需要额外维护产物。

## 2. 决策摘要

| 决策 | 选择 | 理由 |
|---|---|---|
| 判定依据 | 声明期望字段 + 通用截断扫描 | 声明抓「字段缺失」，扫描抓「显示不全」；从接口响应自动推断字段映射误报高 |
| 检查位置 | 步骤级断言 `expect_display` | 与现有断言同构，按页面/弹窗就近检查，容器范围小、误报少 |
| 字段写法 | 纯字符串 + `{label, value}` | 前者写得轻；后者能抓「标签在、值没渲染」 |
| 截断标准 | 被裁切就算 | 对齐测试反馈；个别设计性省略用放行清单处理 |
| 实现方式 | 页面内 JS 一次性检查 | 一次往返、轮询成本低，不依赖页面技术栈 |
| 失败粒度 | 汇总后失败 | 一次跑完看到全部问题，不用逐个重跑 |
| 视觉回归 | 不做 | 基线维护与渲染噪声成本高；本需求不需要 |

## 3. 范围

**做**

- 新增 `runtime/browser/display.py`：检测 JS、轮询、问题汇总。
- `runtime/browser/flow.py` 接入 `expect_display` 断言。
- `runtime/browser/config.py` 对断言结构做启动前校验。
- 流程契约、技能规则、诊断参考、流程模板、使用文档更新。
- 测试夹具与流程测试。

**不做**

- 截图基线视觉回归、像素级布局对比。
- 跨 iframe、Shadow DOM 检查（现有流程同样不支持）。
- 从接口响应自动推断期望字段。
- 流程通过后的独立巡检命令。
- 整页扫描：检查范围限定在声明的容器内。

## 4. 契约

### 4.1 写法

```yaml
- name: 核对订单详情字段
  expect_display:
    locator: {testid: order-detail-dialog}     # 必填：检查容器
    fields:                                     # 与 scan 至少给一项
      - 委托单号                                 # 纯文字：容器内可见、未被裁切
      - {label: 客户名称, value: "${customer_name}"}  # 标签可见，值也出现且非空
      - {label: 收货地址}
    scan: true                                  # 可选，默认 true：容器内截断扫描
    allow_truncate: [备注, {css: ".tag"}]        # 可选：允许截断的文字片段或 CSS
```

### 4.2 规则

- `expect_display` 是断言，不是动作；可以单独成步（零动作 + 断言），也可以挂在有动作的步骤上，与该步骤的其他等待/断言同时生效。
- `locator` 必填，复用现有定位器写法（`testid` / `role` / `text` / `placeholder` / `css`，可用 `in` 引用别名）。容器必须唯一命中且可见；多命中按现有 `LocatorMatchError` 失败。
- `fields` 每项是以下两种之一：
  - 非空字符串：容器内必须存在可见文字包含它。
  - `{label: <非空字符串>, value?: <字符串>}`：`label` 必须可见；写了 `value` 时，替换变量后的值必须出现在容器可见文字中且非空。`value` 解析后为空时只核对标签。
- `fields` 与 `scan` 至少提供一项；`scan` 默认 `true`。显式 `scan: false` 且没有 `fields` 时是配置错误。
- `allow_truncate` 每项是非空字符串（按元素文本包含匹配）或 `{css: "<选择器>"}`；只支持 CSS，不支持其他定位类型。
- `timeout`、`optional`、`allow_api_error` 沿用步骤级现有语义；`${变量}` 照常替换。
- 结构不合法时在启动浏览器前报配置错误（退出码 2）。

## 5. 判定算法

### 5.1 轮询

- 容器用现有定位器解析；容器未出现或不可见时持续重试，直到超时。
- 约每 100ms 执行一次页面内检查；每次检查后调用接口监听 `watch.check()`，接口异常照常快速失败。
- 本轮无问题即通过；超时则用最后一次检查的问题汇总失败。
- 普通脚本异常重试，浏览器被关闭（TargetClosed）按现有规则立即上抛。

### 5.2 字段核对

在容器内收集「可见文本元素」：可见（有尺寸、非 `display:none`、非 `visibility:hidden`）、至少有一个非空白的直接文本节点。隐藏元素不参与可见文字匹配。

| 情况 | 结果 |
|---|---|
| 字符串字段/`label` 的文字出现在某个可见文本元素中 | 通过 |
| 文字只存在于 DOM、所在元素不可见 | `missing_field`，原因注明「存在但不可见」 |
| 文字完全不存在 | `missing_field` |
| `{label, value}` 的标签可见，但值没有出现在容器可见文字中 | `empty_value` |
| 命中的元素本身被裁切 | `truncated`，字段记为该文字 |

值只按「文本出现在容器内」核对，不建立标签与值的精确绑定；同一值在容器别处出现会掩盖缺失，这是接受的取舍。

### 5.3 截断扫描（`scan: true`）

对容器内每个可见文本元素判断，满足任一条件即记为 `truncated`：

1. 自身被裁切：`overflow-x/y` 为 `hidden` 或 `clip`，且 `scrollWidth > clientWidth + 1` 或 `scrollHeight > clientHeight + 1`；或存在 `-webkit-line-clamp` 且内容高度超出可视高度。
2. 被祖先裁切：元素与容器之间（含容器）任一祖先 `overflow-x/y` 为 `hidden` 或 `clip`，且元素矩形超出该祖先的可视矩形 1px 以上。

规则与取舍：

- 可滚动容器（`overflow: auto/scroll`）不算截断：内容可以滚动查看，避免把横向滚动表格、标签条全部判成问题。
- 文本元素带省略号（`text-overflow: ellipsis`）并被裁切算问题；`title`/tooltip 不豁免，与「被裁切就算」的判定一致。
- `allow_truncate` 命中的元素跳过：字符串按元素文本包含匹配，`{css: ...}` 按选择器匹配。
- 跳过 `script`、`style`、`noscript`、`template`、`svg`、`canvas`、`img`、`input`、`textarea`、`select`、`option`、`br`、`hr` 和不可见元素。
- 单次最多报 50 条问题，其余只给数量；扫描最多覆盖 5000 个文本元素，超出部分不扫描并在结果中标记，避免大表格拖慢轮询。

### 5.4 问题记录与失败信息

每条问题带结构化字段：

```json
{
  "kind": "truncated",
  "field": "收货地址",
  "text": "上海市浦东新区…",
  "tag": "td",
  "testid": null,
  "class": "el-table__cell",
  "reason": "scrollWidth 320 > clientWidth 120"
}
```

`kind` 取 `missing_field` / `empty_value` / `truncated`。字段核对产生的问题带 `field`（字段或标签文字）；扫描发现的截断如果不对应声明字段，`field` 为 `null`。

失败时抛 `StepAssertion`：

- 消息示例：`显示检查未通过：缺少字段 委托单号；客户名称 值为空；3 处内容被裁切（收货地址、备注…）`。消息里最多展开 5 条，其余给数量。
- `expected`：`字段齐全且内容未被裁切`。
- `actual`：问题数量摘要。
- `detail.display_problems`：完整问题列表；`detail.scan_limited` 标记是否触达扫描上限。

## 6. 运行时结构

### 6.1 新增 `runtime/browser/display.py`

- `_DISPLAY_JS`：在容器元素内完成字段核对、隐藏判断、截断扫描，返回 `{problems: [...], scan_limited: bool, text_elements: int}`。
- `check_display(page, spec, aliases, timeout_ms, watch=None) -> None`：解析容器、轮询、汇总、抛 `StepAssertion`。
- 容器解析复用 `locator.find`；检查通过 `locator.evaluate(_DISPLAY_JS, args)` 在元素上下文执行，参数为 `{fields, scan, allow_truncate}`。

### 6.2 接入点

- `runtime/browser/flow.py`：`_apply_expects` 增加 `expect_display` 分支，解析顺序与其他断言一致；`_validate_step` 的「至少一个动作或断言」判断已覆盖该断言，无需改动作列表。
- `runtime/browser/config.py`：新增 `_validate_display`，校验 4.2 的结构约束；错误信息指出步骤位置。
- 定位器、驱动、报告、CLI 均不改。

## 7. 诊断与报告

- 报告 JSON 通过 `FlowResult` 序列化自动带出 `failure.detail.display_problems`，无需新字段。
- `diagnosis.md` 新增一节：

  ```markdown
  ## 显示问题
  - [missing_field] 字段 委托单号：容器内未找到该文字
  - [empty_value] 字段 客户名称：标签可见，期望值 "上海某某公司" 未显示
  - [truncated] td.el-table__cell（文本 "上海市浦东新区…"）：scrollWidth 320 > clientWidth 120
  ```

- 「建议」一节增加：显示问题优先核对该字段是否漏渲染、容器/列宽是否不足；设计上允许省略的用 `allow_truncate` 放行。
- 失败截图与 DOM 沿用现有诊断包，无需新增产物。

## 8. 技能与文档

- `skills/_references/browser-flow-contract.md`：第 6 节断言表增加 `expect_display`，给出 4.1 的示例和规则摘要。
- `skills/browser-test/SKILL.md`：执行与铁律里加一条「关键详情页/列表页用 `expect_display` 覆盖字段缺失与截断」；失败处理表补充显示问题的判断方式。
- `skills/_references/browser-diagnosis.md`：判断提示增加显示问题的处理路径（补渲染/调宽度/放行）。
- `skills/_TEMPLATE/browser-flow.example.yaml`：增加一个 `expect_display` 步骤。
- `docs/usage.md` 浏览器测试一章：补一段示例与说明。

## 9. 测试与验收

新增夹具 `tests/browser_fixture/display.html`，覆盖：

| 用例 | 期望 |
|---|---|
| 字段完整、无截断 | 通过 |
| 缺少声明字段 | 失败，`missing_field`，消息含字段名 |
| `{label, value}` 值未渲染 | 失败，`empty_value` |
| `text-overflow: ellipsis` 裁切 | 失败，`truncated` |
| 祖先 `overflow:hidden` 裁切 | 失败，`truncated` |
| `-webkit-line-clamp` 多行裁切 | 失败，`truncated` |
| `allow_truncate` 命中 | 通过 |
| `scan: false` 且容器内有截断 | 通过（只核对字段） |
| 字段延迟 300ms 出现 | 通过（验证轮询） |
| 同时缺少字段 + 截断 | 一次失败，`display_problems` 两类都在 |
| 配置缺少 `locator` / `fields` 与 `scan:false` 同时出现 | 配置错误（退出码 2 路径） |

- 流程测试写在 `tests/test_browser_flow.py`，沿用现有 `page` / `fixture_url` / `tmp_path` 夹具。
- 配置校验测试写在 `tests/test_browser_config.py`。
- 验收：新增用例全绿；`.venv/Scripts/python.exe -m pytest tests -q` 全部通过；用夹具流程手跑一次 `browser.py run`，失败时诊断包含「显示问题」一节。

## 10. 风险与取舍

- **启发式截断**：个别设计性省略（标签、徽标）会命中扫描。用步骤级 `allow_truncate` 或 `scan: false` 处理，并把这类现象记入项目坑库。
- **值核对只比文本**：值在容器别处重复出现会漏报；不建立标签-值绑定，避免引入页面结构约定。
- **动态布局**：动画、弹窗展开过程中截断状态可能瞬时变化；轮询以「最后一次检查」为准，超时前的稳定状态才判失败。
- **检查范围**：只覆盖声明的容器，容器外的字段不会被检查；流程作者按页面补多个断言，保持范围可控。
- **性能**：每轮一次 `evaluate`，扫描设 5000 元素上限；大表格下轮询间隔仍是 100ms 级别。
- **不支持 iframe / Shadow DOM**：与现有流程能力一致，遇到时标记为已知限制。

## 11. 版本与提交

- 新增运行行为，按约定升小版本：`2.1.0` → `2.2.0`，用 `scripts/bump_version.py`，与实现放在同一提交。
- 提交前运行 `tests/test_version_sync.py` 与 `scripts/check_secrets.py`；推送前询问使用者。

## 12. 后续（不在本期）

- 整页/页面级扫描模式（不声明容器）。
- 与截图基线结合的人工/AI 复核。
- 按接口响应自动生成字段清单的辅助工具。
