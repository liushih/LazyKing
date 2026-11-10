# 旧 ERP 模块索引示例

> 本文件是格式示例，不是任何项目的模块清单。不要从这里挑模块名，也不要把它当成本项目的事实。
> 本项目自己的索引写到同目录 `old-erp-map.md`。

## 示例：旧 ERP（hexin）

根目录：`../oldErp/`（与 hexincloud 同级）。主站 `erp_code/modules/`，美国站 `erp_us_code/modules/`。

**每模块一个独立应用**，不是单仓单应用。取证路径一律带模块前缀：`modules/<模块>/app/...`。

### 主站 `erp_code/modules`（21 个）

#### 后端 Laravel（有 `app/Http/Controllers`，11 个）

| 模块 | 控制器 | 大致范围 | 新系统落点（按包名核对，不是猜） |
|---|---|---|---|
| `erp_storage` | 176 | 仓储、库存、入库、库位 | `hexin-wms` |
| `erp_order` | 191 | 订单、出库、发货 | `hexin-oms` |
| `erp_product` | 101 | 商品、SKU、类目 | `hexin-masterdata` |
| `erp_purchase` | 91 | 请购、采购单、到货、质检 | `hexin-oms`（`constant/purchase`、`constant/qc`）+ `hexin-wms`（`qc`、`srm`、`firstleg`） |
| `erp_sales_manage` | 54 | 销售管理 | 待核对 |
| `erp_logistics` | 53 | 物流、渠道、运单 | 待核对（oms/wms 都有物流相关包） |
| `erp_amazon_advertisement` | 58 | 亚马逊广告 | 待核对 |
| `erp_amz_sp_api` | 8 | 亚马逊 SP-API 对接 | 待核对 |
| `erp_olap` | 102 | 报表 + 15 个 `.sql` | 报表独立排期 |
| `erp_site` | 5 | 站点 | 待核对 |
| `erp_auth` | 1 | 认证 | `hexin-auth` |

控制器数只是规模参考，用 `find modules/<m>/app/Http/Controllers -name "*.php" | wc -l` 现算。

#### 纯前端（6 个）

| 模块 | 形态 | 页面入口 |
|---|---|---|
| `erp_html` | React/JSX，webpack | `app/pages/<域>/` |
| `erp_commercial_html` | Vue，`src/` | `src/` |
| `erp_merchants_html` | Vue，`src/` | `src/` |
| `erp_amazon_advertisement_html` | TS，`src/` | `src/` |
| `tms_html` | Vue，`src/` | `src/` |
| `erp_sso_html` | 前端 | `src/` |

`erp_html/app/pages` 覆盖的域：`Advertising` `Finance` `Guidance` `Logistics` `Optimist` `Order` `Product` `Publish` `Purchase` `Puzzle` `Receipt` `Report` `Setup` `Storage` `Tool`。

**业务页面基本都在这里**，不在后端模块的 `resources/views`（那里只有导出、邮件、工具页的 blade）。

#### 小程序 / PDA / 其他（4 个）

| 模块 | 形态 |
|---|---|
| `erp_storage_pda` | uni-app，`src/` |
| `pda` | 小程序壳 |
| `erp_pda_shell` | 壳，无控制器 |
| `erp_image` | **ThinkPHP 3.x**，`Application/Home/{Controller,Logic,Model,View}`，不走 Laravel 那套路径 |

### 美国站 `erp_us_code/modules`（14 个）

`us_wms_amazon_advertisement`、`us_wms_amazon_advertisement_html`、`us_wms_auth`、`us_wms_commercial_html`、`us_wms_hexin_storage`、`us_wms_html`、`us_wms_logistics`、`us_wms_merchants_html`、`us_wms_olap`、`us_wms_order`、`us_wms_product`、`us_wms_purchase`、`us_wms_site`、`us_wms_sso_html`

- 命名带 `us_wms_` 前缀，**不保证与主站同名**：主站 `erp_storage` ↔ 美国站 `us_wms_hexin_storage`
- 主站有、美国站没有：`erp_sales_manage`、`erp_pda_shell`、`erp_storage_pda`、`pda`、`erp_image`、`erp_amz_sp_api`、`tms_html`
- 前端页面同样在 `us_wms_html/app/pages/`（例：`Publish/StockSynchOnline`）
- **库名可能与主站相同**：`us_wms_hexin_storage/测试环境.env` 的 `DB_DATABASE` 也是 `hexin_storage`。连库前确认实例，不能按库名判站点

### 数据权限 Scopes

只有 5 个模块有 `app/Scopes`：`erp_order`、`erp_product`、`erp_purchase`、`erp_logistics`、`erp_olap`（例：`erp_purchase/app/Scopes` 里是 `MerchantIdScope.php` 一类）。

其余模块的数据权限写在控制器查询里，按 `byDataPermission` / `scope` 关键字搜。没有 `app/Scopes` 不等于没有数据权限。

### 连库

`config/database.php` 每模块都有四类连接：`mysql`（`DB_WRITE_*`）、`pgsql`（`PG_DB_*`）、`mongodb`（`MONGO_DB_*`）、`mysqli_clickhouse` / `mysqli_clickhouse_product_center`。

- 业务主库按域分库，例：`erp_storage` → `hexin_storage`，Mongo 库 `hexin`
- 连接信息在部分模块目录下的 `测试环境.env` / `demo环境.env`（不是每个模块都有）
- **账号密码不进任何文档**；查库走 db-access
- `erp_olap` 的 `.sql` 可能指向 ClickHouse/Doris，别拿 MySQL 直接跑

### 新系统对位

- 后端：`hexin-modules/{oms,wms,masterdata,pda,workflow,openapi,auth,ai,gen,job,log,resource}`，包根 `com/hexin/<模块>`
- 前端：`Hexin_ui/src/views/<域>/`、`Hexin_pda_ui/`
- 判断「新系统有没有」读代码，别看模块名；包名里搜关键词最快：`find hexin-modules/<m> -path "*controller*" -iname "*<关键词>*"`
