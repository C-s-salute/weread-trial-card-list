# 接口与字段说明

## 接口

| 接口 | 作用 | 关键字段 |
|---|---|---|
| `GET /web/category/all` | 一级分类导航（SSR） | `CategoryId`、名称 |
| `GET /web/category/<id>` | 分类页，含子分类入口（SSR） | `subCategoryId`、`title` |
| `GET /web/bookListInCategory/<id>?maxIndex=N[&rank=1]` | 分类/榜单列表，每页 20 本 | `bookInfo.*`、`readingCount` |
| `GET /web/book/info?bookId=<id>` | 单本详情 | `totalWords`、`isbn`、`centPrice` |
| `GET /book-detail?type=1&v=<encodeId>` | 书籍分享页（公开 SSR） | `readingStat.readingCount` |

`rank=1` 用于榜单列表（神作榜 `newrating_publish`、神作潜力榜 `newrating_potential_publish`）。
`maxIndex` 0~460 均能翻出 20 本，≥500 返回空 → 单列表真实上限约 480 本。

## 权益字段

| 字段值 | 含义 |
|---|---|
| `paid=1` | 永久可读（已购，优先于付费模式） |
| `payingStatus=1` | 体验卡可读 |
| `payingStatus=2` | 付费会员卡可读 |
| `payingStatus=0` | 免费 |
| `payingStatus=3/4/5/6` | 其他付费模式（语义未完全验证，单独归类为 `X`） |
| `soldout=1` | 已下架，所有视图都要排除 |

## 字段换算

- `推荐值% = newRating / 10`（接口 0~1000，界面显示 93.0%）
- `评价人数 = newRatingCount`（缺省回退 `ratingCount`）
- `累计阅读人数`：**不要**用列表接口的 `readingCount`（中位数仅 23，是短期口径）。必须逐本打开分享页取 `readingStat.readingCount`。
- 价格：依次尝试 `price`（元）、`centPrice`/`realPrice`（分）。
- 出版时间：`publishTime`，形如 `2020-04`，报告只显示到月。

## 已知坑

1. `/web/book/info` 之前必须先 `goto` 首页签发 `wr_skey`，否则返回「用户不存在」且 `totalWords=0`。
2. 未登录时列表接口仍能返回数据，但权益字段可能不全；务必先检查 `wr_vid` cookie。
3. 分类列表翻页会出现空页（限流），原地重试即可，不要把空页当成到底。
4. 同一本书会同时出现在榜单与多个分类里，必须按 `bookId` 去重；再按书名+作者做版本合并。
5. 平台分类本身存在归类偏差（如部分古籍、宗教典籍归入历史），一律以 `category` 字段为准，不做人工改类。
6. 体验卡是限时权益，同一本书的状态会变；报告必须写明抓取时间。
7. HTML 内嵌底图会让文件变大（1~2MB），但保证单文件可分享；底图缺失时要用 CSS 回退，不要留空。

## 去重判定

`same_book(a, b)` 需同时满足：

- 书名核心相同，或一方包含另一方且长度差符合「副标题」规则（短名 ≥ 4 字且覆盖长名 ≥ 80%，或长名以短名开头且多出 ≥ 6 字的营销副标题）。
- 作者关键词集合有交集（去国籍/注释/「著译编」后缀，`·` 分段取首尾段），或相似度 ≥ 0.8。
- 卷册守卫：`第N卷 /（N）/（上）（中）（下）` 之间不合并；「全集/套装/上下册」可与无标记版本合并。
- 期刊守卫：不同年份/期号/增刊/合集不合并。
- 保留排序靠前的版本（推荐值 → 评价人数 → 累计阅读人数降序）。

## 报告结构

- 导航：`全部` + 三个榜单 + 各大类，用 `data-i` 切换，切视图时只显示对应区块（严格相等，不能叠加）。
- `全部` = 所有分类去重后的合集（榜单的书也在其中），按大类 → 子类 → 推荐值降序分块。
- 榜单表多一列「类型」（平台 `category` 原文），末列为「出版时间」。
- 分类配色：类别色相 = 按书目数降序均分 360°，标题用低亮度同色相，卡片底用高亮度同色相。
