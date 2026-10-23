---
name: weread-trial-card-list
version: 1.0.0
description: 微信读书「体验卡可读」高分书单生成器。抓分类页与榜单页，筛出体验卡能免费读的书，剔除低分与下架书、合并同书不同版本，输出可筛选的单文件 HTML 报告（全部 / 神作榜 / 神作潜力榜 / 好评如潮榜 / 各大类）与 6 sheet Excel 清单。当用户提到体验卡能读什么、体验卡快到期了读哪些书值回票价、限时免费书单、免费能读的高分书、不花钱能读哪些书、书荒求推荐、帮我找高分书、神作榜、神作潜力榜、好评如潮、推荐值、累计阅读人数、微信读书书单、体验卡和会员卡区别时使用。Build a WeRead trial-card readable book list from category and rank pages, then export a single-file HTML report and Excel. 不适用于书架购书方案与个人阅读统计——那类需求请用 weread-buybooks。
---

# 微信读书 · 体验卡可读书目

抓取微信读书分类页与榜单页的公开列表数据，筛出「体验卡可读（`payingStatus=1`）」且未下架的书，过滤低分、合并同书不同版本，输出单文件 HTML 报告与 Excel 清单。

## 产物

| 文件（位于 `WEREAD_WORK`） | 内容 |
|---|---|
| `_discover_pool.json` | 候选池，含权益字段、平台分类、deepLink |
| `_book_extra.json` | 逐本补抓的字数/ISBN/格式 |
| `_book_read.json` | 逐本补抓的累计阅读人数 |
| `微信读书_体验卡可读高分书.html` | 单文件报告：全部 / 三大榜单 / 各大类 |
| `微信读书_体验卡可读高分书.xlsx` | 6 个 sheet：概览、三榜单、全部、分类汇总 |

## 前置条件

1. Python 3.10+，依赖 `playwright`、`openpyxl`（`pip install -r requirements.txt`）；浏览器用系统 Chrome/Edge 或 Playwright 内置 chromium。
2. 首次运行需扫码登录（登录态只存在浏览器 profile 目录，不落明文 cookie）。

## 环境变量

所有路径都不写死；默认数据目录在用户主目录，**不会写进仓库**：

| 变量 | 默认 | 说明 |
|---|---|---|
| `WEREAD_WORK` | `~/.weread-trial-card-list/data` | 数据与报告目录 |
| `WEREAD_PROFILE` | `~/.weread-trial-card-list/profile` | 浏览器 profile（登录态）；相对路径按 `WEREAD_WORK` 解析 |
| `WEREAD_BROWSER` | `msedge` → `chrome` → chromium | 浏览器通道 |
| `PER_CAT` | `300` | 普通分类每类抓取上限 |
| `DEEP_LIMIT` | `480` | 重点分类与子分类上限（接口硬上限） |
| `DEEP_CATS` | `1100000,1500000,600000,1200000` | 需要叠加子分类的重点分类 ID |
| `SLEEP` | `0.3` | 请求间隔秒 |
| `WEREAD_FIRE_IMAGE` | 空 | 可选：好评如潮榜卡片底图路径；缺省用 CSS 斜纹回退 |

## 执行顺序

无需设置 `WEREAD_WORK` 即可运行（默认写到用户主目录）；如需指定目录，先设 `$env:WEREAD_WORK = "D:\path\to\data"`。

```bash
python scripts/login.py                      # 扫码登录，已有登录态会直接退出
python scripts/fetch_pool.py                 # 抓分类/榜单 → _discover_pool.json
python scripts/fetch_extra.py                # 字数等详情 → _book_extra.json
python scripts/fetch_readcount.py            # 累计阅读人数 → _book_read.json
python scripts/build_html.py                 # → 单文件 HTML
python scripts/build_excel.py                # → Excel（复用 build_html 的口径函数）
```

也可 `python scripts/run_pipeline.py` 一次跑完；加 `--reuse` 跳过抓取、只重出报告。
全量抓取约 2400+ 本候选、逐本补抓 1700+ 本，耗时以小时计，补抓脚本支持断点续跑。

## 口径（改动前先与用户确认）

1. **权益**：`paid=1` 永久可读；`payingStatus=1` 体验卡可读；`2` 付费会员卡；`0` 免费；其他归「其他付费模式」。本清单只取 `T` 且 `soldout != 1`。
2. **评分**：`推荐值 = newRating / 10`（接口 0~1000）。剔除 `ratingCount = 0` 与推荐值 < 60% 的书。
3. **去重**：书名核心（去括注、标点）相似 + 作者关键词有交集，只留评分最高的版本；`第N卷 /（N）/ 上中下册` 与 `年第N期 / 增刊 / 合集` 视为不同书，不合并。
4. **分类**：大类与子类都取平台书目元数据 `category`（形如 `历史-历史典籍`），不按抓取来源命名。
5. **榜单**：神作榜 = 推荐值 ≥ 90% 且累计阅读人数 ≥ 5000；神作潜力榜 = ≥ 90% 且 < 5000；好评如潮榜 = 85%~90%（含 85，不含 90）且 ≥ 1500。
6. **累计阅读人数**：列表接口的 `readingCount` 不是累计口径（中位数仅 23），必须用书籍分享页的 `readingStat.readingCount`。
7. **排序**：榜单与分类内均按推荐值降序、同分按累计阅读人数降序。

## 视觉约定

- 按钮激活态与标题卡片同向渐变（重色在左、浅色在右）；大类用淡彩底 + 深色类名（对比 ≥ 7:1）。
- 神作榜=鎏金多段高光，神作潜力榜=香槟金，好评如潮榜=火焰底图 + 左侧白纱，全部=微信读书蓝。
- 书名 Arial 常规 15.5px、深墨 `#1c2534`、带书名号；其余信息 12.5px；推荐值五档配色（≥90 金 / 85–90 大红 / 80–85 淡红 / 70–80 绿 / 60–70 淡蓝）。
- 榜单表在书名列右侧有「类型」列；末列表头为「出版时间」。

## 约束

- 不要把任何绝对路径、用户名、cookie、书架数据写进脚本或报告文案；报告脚注只描述接口口径。
- 登录态只留在 profile 目录；不要导出 cookie。
- 抓取失败原地重试，连续失败才跳过；补抓脚本都要支持断点续跑（已有记录不重复请求）。
- 修改口径或视觉方案前，先给用户可对比的方案，确认后再重建。

## 安全与合规

**凭据与隐私**

- 登录只走扫码；cookie 由 Playwright 持久化在 `WEREAD_PROFILE`（默认在用户主目录），不进仓库、不打印、不导出。
- 脚本不读取书架、不读取用户 ID、不写任何账号信息；`has_login()` 只判断 `wr_vid` 是否存在。
- 仓库内不得出现：绝对路径、用户名、书币/书架截图、抓取数据、生成的 HTML/Excel。

**数据隔离**

- 默认数据目录 `~/.weread-trial-card-list/data` 位于仓库之外；`WEREAD_WORK` 只允许通过环境变量覆盖。
- `.gitignore` 已排除 profile、三份 JSON 缓存、报告产物与本地 env 文件；发布前用 `git status` 复核无数据文件被暂存。

**抓取行为**

- 只访问公开分类页/榜单页/书籍详情与分享页，不绕过付费、不抓正文、不批量下载资源。
- 保留 `SLEEP` 间隔与失败重试；不要把 `SLEEP` 调到 0。
- 抓取结果仅供个人研究参考，不转载、不再分发原始数据；报告中注明抓取时间与「权益可能变化」。

**发布前自查**

1. `git ls-files` 中没有 `*.xlsx`、`*体验卡*.html`、`_discover_pool.json`、`_book_extra.json`、`_book_read.json`、`fire_bg.jpg`。
2. 全仓库搜索本机用户名、盘符路径（`C:\\`、`D:\\`）、`wr_skey`、`cookie`，确认无命中。
3. `python -m py_compile scripts/*.py` 通过；`python scripts/run_pipeline.py --reuse` 可在无网络时用缓存出报告。
4. 确认没有提交 `__pycache__` 与虚拟环境目录。

## 验收

1. `build_html.py` 打印的书目数、大类数、榜单数应与 `build_excel.py` 的概览一致。
2. 浏览器打开 HTML：`全部` 视图不重复包含榜单专属卡片；点击任一榜单/分类按钮只显示对应区块；书名链接可跳转。
3. 抽查 3 本：推荐值、评价人数、阅读人数、字数与微信读书页面一致；重复版本只出现一次。
4. Excel 各 sheet 行数与 HTML 对应视图一致。

接口细节、字段含义与历史坑见 [references/api-notes.md](references/api-notes.md)。
