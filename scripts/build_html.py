# -*- coding: utf-8 -*-
"""把「体验卡可读」书目渲染成单文件 HTML（列表式 + 分类按钮 + 三大榜单）。

视图：全部 / 神作榜 / 神作潜力榜 / 好评如潮榜 / 各大类。
每个视图内按子分类分块（每块一种配色），块内按推荐值降序，展示评分、评价人数、
阅读人数、字数、价格、作者等字段。书名带书名号并链接到微信读书该书页面。

字数来自 _book_extra.json（fetch_extra.py 逐本补抓）。
用法：WEREAD_WORK=<数据目录> python build_html.py
"""
import base64
import html
import json
import math
import os
import re
import sys
import time
from difflib import SequenceMatcher

import wrconfig

WORK = str(wrconfig.WORK)
POOL = '_discover_pool.json'
EXTRA = '_book_extra.json'
READ = '_book_read.json'
# 可选的好评如潮榜卡片底图（不给则用 CSS 斜纹回退）
FIRE = os.environ.get('WEREAD_FIRE_IMAGE') or ''
OUT = '微信读书_体验卡可读高分书.html'
SUB_TOP = '未细分'

# 榜单口径（推荐值按 % 计；阅读人数 = 累计阅读人数 readingCount）
RANKS = [
    ('神作榜', '推荐值 ≥ 90.0% 且 累计阅读人数 ≥ 5000',
     lambda b: (b.get('rating') or 0) >= 90 and (b.get('_read') or 0) >= 5000),
    ('神作潜力榜', '推荐值 ≥ 90.0% 且 累计阅读人数 < 5000',
     lambda b: (b.get('rating') or 0) >= 90 and b.get('_read') is not None
     and b['_read'] < 5000),
    ('好评如潮榜', '85.0% ≤ 推荐值 < 90.0% 且 累计阅读人数 ≥ 1500',
     lambda b: 85 <= (b.get('rating') or 0) < 90 and (b.get('_read') or 0) >= 1500),
]


def norm_title(t):
    """去重用书名归一：去空白、去首尾书名号。"""
    t = re.sub(r'\s+', '', t or '')
    return t.strip('《》')


def title_core(t):
    """去重比对用书名核心：去掉括注（如「（果麦经典）」「（全三册）」）与标点。"""
    t = norm_title(t)
    t = re.sub(r'[（(【\[][^）)】\]]*[）)】\]]', '', t)
    return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', t)


def author_keys(a):
    """作者归一为可比较的关键词集合：去国籍/注释、空白，取全名与首尾段（「阿尔贝·加缪」→ 加缪）。"""
    a = re.sub(r'\[[^\]]*\]|【[^】]*】|\([^)]*\)|（[^）]*）', '', a or '')
    a = re.sub(r'\s+', '', a)
    parts = [p for p in re.split(r'[·•・]', a) if p]
    keys = set([a]) if a else set()
    if parts:
        keys.update([parts[0], parts[-1]])
    keys = {re.sub(r'(著|译|注|编|等|主编|译注|审校|校注|编著)$', '', k) for k in keys}
    return {k for k in keys if len(k) >= 2}


NUM = r'[\d一二三四五六七八九十百壹贰叁肆伍陆柒捌玖]+'
VOL_RE = re.compile(r'第\s*(' + NUM + r')\s*(?:卷|册|部)')
BARE_RE = re.compile(r'[（(【\[]\s*第?\s*(' + NUM + r')\s*[）)】\]]')
PART_RE = re.compile(r'[（(【\[]\s*([上中下])\s*(?:[卷册部])?\s*[）)】\]]')
SET_RE = re.compile(r'(全集|全\s*' + NUM + r'\s*(?:卷|册|部)|套装|共\s*' + NUM + r'\s*(?:卷|册|部)|上下\s*[卷册部])')
SERIAL_RE = re.compile(r'\d{4}\s*年[^\s）)】\]]*|第\s*[一二三四五六七八九十\d]+\s*期|增刊[^\s）)】\]]*|合集')


def extent_tag(t):
    """篇幅标记：分卷（第N卷/（N）/（上）（中）（下））优先，其次整套（全集/全N卷/套装/上下册）。"""
    t = t or ''
    m = VOL_RE.search(t) or BARE_RE.search(t) or PART_RE.search(t)
    if m:
        return 'part:' + m.group(1)
    if SET_RE.search(t):
        return 'all'
    return ''


def serial_tag(t):
    """期刊/合集标记：不同年份或期号不是同一本书。"""
    ms = SERIAL_RE.findall(t or '')
    return '|'.join(sorted({re.sub(r'\s+', '', x) for x in ms}))


def same_book(a, b):
    """书名核心 + 作者关键词重合度判定是否为同一本书的不同版本。"""
    # 期刊分期：不同年份/期号视为不同书
    sa, sb = a['_serial'], b['_serial']
    if sa and sb and sa != sb:
        return False
    # 卷册守卫：整套（全集/套装）可与无标记版本合并，但与分卷（第N卷/（N）/上中下）不合并
    ea, eb = a['_ext'], b['_ext']
    if ea or eb:
        if ea != eb and not ((ea == 'all' and not eb) or (eb == 'all' and not ea)):
            return False
    ca, cb = a['_core'], b['_core']
    if not ca or not cb:
        return False
    if ca == cb:
        ok_title = True
    elif ca in cb or cb in ca:
        short, long_ = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
        ok_title = (len(short) >= max(4, math.ceil(0.8 * len(long_)))
                    # 前缀相同且尾巴是副标题式营销词（如「西西弗神话」+ 16 字推荐语）
                    or (long_.startswith(short) and len(short) >= 4 and len(long_) - len(short) >= 6))
    else:
        ok_title = False
    if not ok_title:
        return False
    ka, kb = a['_akeys'], b['_akeys']
    if not ka or not kb:
        return False
    if ka & kb:
        return True
    for x in ka:
        for y in kb:
            if min(len(x), len(y)) >= 3 and SequenceMatcher(None, x, y).ratio() >= 0.8:
                return True
    return False


def dedup_keys(b):
    """预处理去重所需的四个键。"""
    t = b.get('title')
    b['_core'] = title_core(t)
    b['_akeys'] = author_keys(b.get('author'))
    b['_ext'] = extent_tag(t)
    b['_serial'] = serial_tag(t)


def split_cat(b):
    c = (b.get('category') or '').strip()
    if '-' in c:
        a, s = c.split('-', 1)
        return a.strip() or SUB_TOP, s.strip() or SUB_TOP
    if c:
        return c, SUB_TOP
    return (b.get('discoverCat') or SUB_TOP), SUB_TOP


def css():
    return """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2534;--mut:#7b8798;--line:#e6eaf0;--brand:#2f7cf6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-size:14px;
  font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",system-ui,sans-serif}
header{padding:26px 30px 16px;color:#fff;
  background:linear-gradient(135deg,#2058cf 0%,#2f7cf6 48%,#63a2ff 100%)}
h1{margin:0 0 8px;font-size:24px;letter-spacing:.5px}
.meta{font-size:14.5px;line-height:1.9;opacity:.93}
.meta b{font-weight:600}
nav{position:sticky;top:0;z-index:9;padding:10px 30px 6px;background:rgba(255,255,255,.95);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.row{display:flex;flex-wrap:wrap;gap:7px;align-items:center;padding:3px 0}
.lbl{font-size:13px;color:var(--mut);min-width:38px;flex:none}
.tab{display:inline-flex;align-items:center;gap:7px;padding:7px 13px;border-radius:999px;
  border:1px solid var(--line);background:#fff;color:var(--ink);font-size:15px;cursor:pointer;
  transition:.15s;font-family:inherit}
.tab:hover{border-color:#c3ceda;transform:translateY(-1px)}
.tab .dot{width:9px;height:9px;border-radius:50%;flex:none}
.tab .n{font-size:13px;color:var(--mut);font-variant-numeric:tabular-nums}
.tab.on{background:var(--brand);border-color:var(--brand);color:#fff;box-shadow:0 4px 12px rgba(31,56,100,.22)}
.tab.on .n{color:rgba(255,255,255,.82)}
/* 有主题色的按钮：激活态整块渐变，重色在左、浅色在右，与标题卡片同向 */
.tab.grad.on{background:linear-gradient(90deg,var(--tg2),var(--tg1) 94%);
  border-color:var(--tg2);color:#1f2937;box-shadow:0 4px 12px rgba(31,41,55,.16)}
.tab.grad.on .n{color:rgba(0,0,0,.5)}
.tab.rk0 .dot{background:linear-gradient(135deg,#f8e7b0,#d9a92c)}
.tab.rk1 .dot{background:linear-gradient(135deg,#fdf5c4,#e9c93c)}
.tab.rk2 .dot{background:linear-gradient(135deg,#f9d6d6,#d4453f)}
.tab.rk0{--tg1:#f8e7b0;--tg2:#d9a92c}
.tab.rk1{--tg1:#fdf5c4;--tg2:#e9c93c}
.tab.rk2{--tg1:#f9d6d6;--tg2:#d4453f}
main{padding:22px 30px 44px}
.cat{display:none;--h:210;--g1:hsl(var(--h),72%,96%);--g2:hsl(var(--h),56%,82%);
  --sh:hsl(var(--h),45%,90%)}
.cat.show{display:block}
/* 标题卡片：h2 + 口径说明 作为整体，渐变由重色（左）到浅色（右） */
.cat .head{margin:10px 0 14px;padding:12px 18px;border-radius:12px;
  background:linear-gradient(90deg,var(--g2),var(--g1) 92%);box-shadow:0 4px 14px var(--sh)}
.cat h2{font-size:19px;margin:0;display:flex;align-items:baseline;gap:10px;
  flex-wrap:wrap;color:#1c2534}
.cat h2>*{flex:none}
.cat h2 .cnt{color:rgba(0,0,0,.55);font-size:13.5px;font-weight:600;white-space:nowrap}
.cat .rule{color:rgba(0,0,0,.6);font-size:13px;margin:4px 0 0}
/* 三大榜单：金 / 黄 / 大红 渐变 */
.cat.rk0{--h:42;--g1:#f8e7b0;--g2:#d9a92c;--sh:#e7d29a}
.cat.rk1{--h:48;--g1:#fdf5c4;--g2:#e9c93c;--sh:#ece0a8}
.cat.rk2{--h:3;--g1:#f9d6d6;--g2:#d4453f;--sh:#eec4c2}
/* 神作榜：鎏金质感（左端保持中金亮度，避免黑边压住粗体标题） */
.cat.rk0 .head{background:linear-gradient(90deg,#f0d47a 0%,#fffce6 13%,#e6bf4e 30%,
  #fffae0 48%,#e1b740 66%,#fdf3c4 84%,#ead292 100%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.8),inset 0 -1px 0 rgba(150,112,20,.22),
  0 5px 16px rgba(176,136,36,.38)}
.cat.rk0 h2{text-shadow:0 1px 0 rgba(255,255,255,.5)}
.tab.rk0.on{background:linear-gradient(90deg,#f0d47a 0%,#fffce6 22%,#e6bf4e 42%,#fff3c4 60%,
  #e2ba44 80%,#f7e9bb 100%);
  border-color:#d3ac45;box-shadow:inset 0 1px 0 rgba(255,255,255,.8),0 4px 12px rgba(176,136,36,.42)}
/* 神作潜力榜：香槟黄金属质感 */
.cat.rk1 .head{background:linear-gradient(90deg,#f5e98c 0%,#fffff0 14%,#ecd968 32%,
  #fffee2 50%,#e8d35c 68%,#fefbdc 86%,#efe08f 100%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.85),inset 0 -1px 0 rgba(150,125,20,.2),
  0 5px 16px rgba(196,170,40,.33)}
.cat.rk1 h2{text-shadow:0 1px 0 rgba(255,255,255,.55)}
.tab.rk1.on{background:linear-gradient(90deg,#f5e98c 0%,#fffff0 22%,#ecd968 42%,#fffee2 60%,
  #e8d35c 80%,#fdf8d0 100%);
  border-color:#dcc94f;box-shadow:inset 0 1px 0 rgba(255,255,255,.85),0 4px 12px rgba(196,170,40,.4)}
/* 好评如潮榜：火焰图底色（fire_bg.jpg 内嵌，见下方附加样式；无图时回退为斜向条纹） */
.cat.rk2 .head{background:
  repeating-linear-gradient(135deg,
    rgba(200,16,46,.17) 0 9px,
    rgba(255,122,0,.20) 9px 18px,
    rgba(255,196,40,.26) 18px 27px,
    rgba(255,255,255,0) 27px 36px),
  linear-gradient(90deg,#fff4ee 0%,#ffe3d8 55%,#fff9f2 100%);
  box-shadow:inset 0 0 0 1px rgba(200,50,40,.18),0 4px 14px rgba(212,69,63,.20)}
.cat.rk2 h2{color:#9c1017}
/* 全部：沿用页头蓝色方案 */
.cat.all .head{background:linear-gradient(135deg,#2058cf 0%,#2f7cf6 48%,#63a2ff 100%);
  box-shadow:0 5px 16px rgba(47,124,246,.32)}
.cat.all h2{color:#fff}
.cat.all h2 .cnt{color:rgba(255,255,255,.82)}
.cat.all .rule{color:rgba(255,255,255,.9)}
.tw{overflow-x:auto;background:var(--card);border:1px solid hsl(var(--h),34%,80%);
  border-radius:10px;box-shadow:0 2px 10px hsl(var(--h),42%,88%)}
table{width:100%;border-collapse:collapse;font-size:12.5px;min-width:960px}
thead th{position:static;background:hsl(var(--h),46%,95%);color:hsl(var(--h),38%,30%);
  font-weight:600;font-size:11.5px;text-align:left;padding:9px 10px;white-space:nowrap;
  border-bottom:1px solid hsl(var(--h),34%,84%)}
thead th.r{text-align:right}
tr.grp td{padding:10px 10px 7px;background:hsl(var(--h),44%,97.5%);border-top:1px solid var(--line);
  border-left:4px solid transparent}
tr.grp .chip{display:inline-block;padding:3px 11px;border-radius:999px;font-size:12px;font-weight:600}
tr.grp .cnt{color:var(--mut);font-size:11.5px;margin-left:8px}
tr.grp.cat-row td{padding:9px 12px 8px;border-top:1px solid var(--line)}
tr.grp.cat-row .catname{font-size:14.5px;font-weight:700;color:#1c2534;letter-spacing:.6px}
tbody tr.bk:hover td{background:#f7f9fc}
tbody tr.bk td{padding:8px 10px;border-bottom:1px dashed #eef1f5;vertical-align:middle}
td.i{color:#b9c2cf;font-size:11px;text-align:right;width:46px;font-variant-numeric:tabular-nums}
td.t{max-width:360px}
td.ty{color:#5f6b7d;font-size:12px;line-height:1.5;max-width:150px}
.cat.rank table{min-width:1080px}
td.t a{color:#1c2534;text-decoration:none;font-weight:400;font-size:15.5px;letter-spacing:.3px;
  font-family:Arial,Helvetica,"Microsoft YaHei",sans-serif}
td.t a:hover{text-decoration:underline;color:#b3131a}
td.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rate{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11.5px;font-weight:700;
  background:#e8f1fa;color:#2a6ba8}
.rate.gold{background:#fbeec4;color:#8a6100;box-shadow:inset 0 0 0 1px #e6c96f}
.rate.red{background:#fce0e0;color:#b3131a}
.rate.salmon{background:#fdeeea;color:#c25b4a}
.rate.green{background:#e6f5e9;color:#1c7a3b}
.rate.blue{background:#e8f1fa;color:#2a6ba8}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:13.5px;white-space:nowrap}
footer{padding:0 30px 48px;color:var(--mut);font-size:13.5px;line-height:2}
footer b{color:#44506a}
"""


def fire_css():
    """好评如潮榜：可选底图（WEREAD_FIRE_IMAGE）内嵌 base64，左侧白色纱层保证文字可读。"""
    if not FIRE:
        return ''
    p = FIRE if os.path.isabs(FIRE) else os.path.join(WORK, FIRE)
    if not os.path.isfile(p):
        return ''
    with open(p, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    return ('.cat.rk2 .head{background-image:'
            'linear-gradient(90deg,rgba(255,255,255,.97) 0%,rgba(255,255,255,.94) 34%,'
            'rgba(255,255,255,.28) 64%,rgba(255,255,255,0) 86%),'
            'url("data:image/jpeg;base64,' + b64 + '");'
            'background-size:cover;background-position:center center;'
            'box-shadow:inset 0 0 0 1px rgba(226,120,60,.5),0 4px 14px rgba(212,69,63,.24)}\n'
            '.cat.rk2 h2{color:#8f0b12}\n'
            '.cat.rk2 .rule{color:#7d2f22}\n'
            '.cat.rk2 h2 .cnt{color:rgba(110,30,15,.7)}\n')


def hsl(h, s, l):
    return 'hsl(' + str(int(round(h)) % 360) + ' ' + str(int(s)) + '% ' + str(int(l)) + '%)'


def num(n):
    if not n:
        return '—'
    n = int(n)
    if n >= 10000:
        return ('%.1f万' % (n / 10000.0)).replace('.0万', '万')
    return str(n)


def words(n):
    if not n:
        return '—'
    n = int(n)
    return ('%.1f万字' % (n / 10000.0)).replace('.0万字', '万字') if n >= 10000 else str(n) + ' 字'


def title_of(t):
    t = (t or '').strip()
    return t[1:-1] if t.startswith('《') and t.endswith('》') else t


def row_html(b, idx, extra, with_type=False):
    """渲染一本书的表格行。with_type=True 时在书名列右侧加「类型」列（榜单视图用）。"""
    t = title_of(b.get('title'))
    link = b.get('deepLink') or 'https://weread.qq.com'
    r = b.get('rating')
    if r is None:
        rate = '—'
    else:
        cls = ('gold' if r >= 90 else 'red' if r >= 85 else
               'salmon' if r >= 80 else 'green' if r >= 70 else 'blue')
        rate = '<span class="rate ' + cls + '">%.1f%%</span>' % r
    w = (extra.get(b['bookId']) or {})
    price = ('¥%.2f' % b['price']) if b.get('price') else '—'
    pub = (b.get('publishTime') or '')[:7] or '—'
    typ = b.get('category') or (b['_cat'] + '-' + b['_sub'] if b.get('_sub') else b['_cat'])
    cell_ty = '<td class="ty">' + html.escape(typ) + '</td>' if with_type else ''
    return ('<tr class="bk"><td class="i">' + str(idx) + '</td>'
            '<td class="t"><a href="' + html.escape(link) + '" target="_blank" rel="noopener">《'
            + html.escape(t) + '》</a></td>' + cell_ty +
            '<td>' + rate + '</td>'
            '<td class="r">' + num(b.get('ratingCount')) + '</td>'
            '<td class="r">' + num(b.get('_read')) + '</td>'
            '<td class="r">' + words(w.get('totalWords')) + '</td>'
            '<td class="r">' + price + '</td>'
            '<td>' + html.escape(b.get('author') or '—') + '</td>'
            '<td class="r">' + pub + '</td>'
            '<td></td></tr>')


def sub_bar(label, n, hue, cols=10):
    return ('<tr class="grp"><td colspan="' + str(cols) + '" style="border-left-color:'
            + hsl(hue, 62, 62) + '">'
            '<span class="chip" style="background:' + hsl(hue, 82, 93) + ';color:'
            + hsl(hue, 55, 31) + '">' + html.escape(label) + '</span>'
            '<span class="cnt">' + str(n) + ' 本</span></td></tr>')


def table_wrap(body, with_type=False):
    head = ('<thead><tr><th class="r">#</th><th>书名（点击跳转）</th>'
            + ('<th>类型</th>' if with_type else '')
            + '<th>推荐值</th>'
            '<th class="r">评价人数</th><th class="r">阅读人数</th><th class="r">字数</th>'
            '<th class="r">价格</th><th>作者</th><th class="r">出版时间</th><th></th></tr></thead>')
    return '<div class="tw"><table>' + head + '<tbody>' + ''.join(body) + '</tbody></table></div>'


def by_rating(rows):
    return sorted(rows, key=lambda b: (-(b.get('newRating') or 0), -(b.get('_read') or 0)))


def table_for(books, extra, hue_map, with_type=False):
    """按子分类分块渲染成一张表。hue_map: 子分类 -> 色相。"""
    subs = {}
    for b in books:
        subs.setdefault(b['_sub'], []).append(b)
    cols = 11 if with_type else 10
    body = []
    for s in sorted(subs, key=lambda s: (-len(subs[s]), s)):
        rows = by_rating(subs[s])
        body.append(sub_bar(s or SUB_TOP, len(rows), hue_map.get(s, 0), cols))
        body.extend(row_html(b, i, extra, with_type) for i, b in enumerate(rows, 1))
    return table_wrap(body, with_type)


def table_all(books, extra, cat_order, cat_hue):
    """「全部」视图：大类分块 → 子类分块 → 推荐值降序。"""
    grp = {}
    for b in books:
        grp.setdefault(b['_cat'], []).append(b)
    body = []
    for c in cat_order:
        rows = grp.get(c) or []
        if not rows:
            continue
        hue_c = cat_hue[c]
        body.append('<tr class="grp cat-row"><td colspan="10" style="background:' + hsl(hue_c, 48, 93)
                    + ';border-left-color:' + hsl(hue_c, 58, 52)
                    + '"><span class="catname" style="color:' + hsl(hue_c, 58, 28) + '">'
                    + html.escape(c) + '</span>'
                    '<span class="cnt">' + str(len(rows)) + ' 本</span></td></tr>')
        subs = {}
        for b in rows:
            subs.setdefault(b['_sub'], []).append(b)
        for j, s in enumerate(sorted(subs, key=lambda s: (-len(subs[s]), s))):
            rs = by_rating(subs[s])
            body.append(sub_bar(s or SUB_TOP, len(rs), (hue_c + 360.0 * j / max(len(subs), 1)) % 360))
            body.extend(row_html(b, i, extra) for i, b in enumerate(rs, 1))
    return table_wrap(body)


def build(payload, extra, read):
    raw = [b for b in payload['books'] if b['rights'] == 'T' and b.get('soldout') != 1]
    ts = time.strftime('%Y-%m-%d %H:%M', time.localtime(payload['fetchedAt']))

    for b in raw:
        b['_cat'], b['_sub'] = split_cat(b)
        b['_read'] = (read.get(b['bookId']) or {}).get('readingCount')

    # 剔除无评分 / 低分（推荐值 < 60%）
    rated = [b for b in raw if (b.get('rating') or 0) >= 60 and (b.get('ratingCount') or 0) > 0]
    n_low = len(raw) - len(rated)
    # 同书不同版本去重：书名核心相似 + 作者关键词重合，按评分降序保留最好的版本
    rated.sort(key=lambda b: (-(b.get('rating') or 0), -(b.get('ratingCount') or 0),
                              -(b.get('_read') or 0)))
    for b in rated:
        dedup_keys(b)
    kept = []
    for b in rated:
        if any(same_book(b, k) for k in kept):
            continue
        kept.append(b)
    books = kept
    n_dup = len(rated) - len(books)

    grp = {}
    for b in books:
        grp.setdefault(b['_cat'], []).append(b)
    cat_order = sorted(grp, key=lambda k: -len(grp[k]))
    n_cat = max(len(cat_order), 1)
    cat_hue = {c: 360.0 * i / n_cat for i, c in enumerate(cat_order)}

    nav_rank, nav_cat, secs = [], [], []
    nav_rank.append('<button class="tab grad all" data-i="all" style="--tg1:#e9f1ff;--tg2:#8fb4f5">'
                    '<span class="dot" style="background:#2f7cf6"></span>全部'
                    '<span class="n">' + str(len(books)) + '</span></button>')

    # ---- 全部（独立卡片：全部书目，不含三个榜单）----
    secs.append('<section class="cat all show" data-i="all" style="--h:220;--g1:#e9f1ff;--g2:#8fb4f5;'
                '--sh:#cfe0fa">'
                '<div class="head"><h2>全部书目'
                '<span class="cnt">' + str(len(books)) + ' 本 / ' + str(len(cat_order)) + ' 个大类</span></h2>'
                '<p class="rule">体验卡可读、推荐值 ≥ 60%、已去除重复版本的全部书目；'
                '按大类（书多在前）→ 子类（本数降序）分块，块内按推荐值降序。三个榜单的书同样计在里面，'
                '榜单视图只是其中的高分切片。</p></div>'
                + table_all(books, extra, cat_order, cat_hue) + '</section>')

    # ---- 三大榜单 ----
    for k, (name, rule, fn) in enumerate(RANKS):
        sel = [b for b in books if fn(b)]
        sel.sort(key=lambda b: (-(b.get('newRating') or 0), -(b.get('_read') or 0)))
        key = 'r' + str(k)
        hue = 42 + k * 96
        nav_rank.append('<button class="tab grad rk' + str(k) + '" data-i="' + key + '"><span class="dot">'
                        '</span>' + name
                        + '<span class="n">' + str(len(sel)) + '</span></button>')
        subs_r = sorted({b['_sub'] for b in sel})
        n_r = max(len(subs_r), 1)
        hue_map = {s: (hue + 360.0 * j / n_r) % 360 for j, s in enumerate(subs_r)}
        secs.append('<section class="cat rank rk' + str(k) + '" data-i="' + key
                    + '" style="--h:' + str(int(round(hue))) + '">'
                    + '<div class="head"><h2>' + name
                    + '<span class="cnt">' + str(len(sel)) + ' 本</span></h2>'
                    + '<p class="rule">口径：' + rule + '；按平台子类分块，块内按推荐值降序，同分按阅读人数降序</p></div>'
                    + table_for(sel, extra, hue_map, True) + '</section>')

    # ---- 大类 ----
    for ci, cat in enumerate(cat_order):
        hue_c = cat_hue[cat]
        col_c = hsl(hue_c, 62, 46)
        nav_cat.append('<button class="tab grad" data-i="c' + str(ci) + '" style="--tg1:'
                       + hsl(hue_c, 64, 94) + ';--tg2:' + hsl(hue_c, 55, 74)
                       + '"><span class="dot" style="background:'
                       + col_c + '"></span>' + html.escape(cat) + '<span class="n">'
                       + str(len(grp[cat])) + '</span></button>')
        subs = sorted({b['_sub'] for b in grp[cat]})
        n_sub = max(len(subs), 1)
        hue_map = {s: (hue_c + 360.0 * j / n_sub) % 360 for j, s in enumerate(subs)}
        secs.append('<section class="cat" data-i="c' + str(ci) + '" style="--h:' + str(int(round(hue_c))) + '">'
                    + '<div class="head"><h2 style="color:' + hsl(hue_c, 68, 23) + '">'
                    + html.escape(cat)
                    + '<span class="cnt">' + str(len(grp[cat])) + ' 本 / '
                    + str(len(subs)) + ' 个子类</span></h2>'
                    + '<p class="rule">按子分类分块（每块一种配色），块内按推荐值降序</p></div>'
                    + table_for(grp[cat], extra, hue_map) + '</section>')

    n_words = len([b for b in books if (extra.get(b['bookId']) or {}).get('totalWords')])
    head = (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>微信读书 · 体验卡可读书目</title><style>' + css() + fire_css() + '</style></head><body>'
        '<header><h1>微信读书 · 体验卡可读书目</h1><div class="meta">'
        '数据抓取 <b>' + ts + '</b> · 候选池 <b>' + str(len(payload['books'])) + '</b> 本<br>'
        '体验卡可读且未下架 <b>' + str(len(raw)) + '</b> 本 → 剔除无评分/推荐值<60% <b>' + str(n_low)
        + '</b> 本、同书名同作者重复版本 <b>' + str(n_dup) + '</b> 本 → 保留 <b>' + str(len(books)) + '</b> 本<br>'
        + str(len(cat_order)) + ' 个大类 · 字数已补抓 <b>' + str(n_words) + '</b> 本<br>'
        '按钮切换视图；书名可点击直达微信读书该书页面'
        '</div></header><nav>'
        '<div class="row"><span class="lbl">全部/榜单</span>' + ''.join(nav_rank) + '</div>'
        '<div class="row"><span class="lbl">分类</span>' + ''.join(nav_cat) + '</div>'
        '</nav><main>' + ''.join(secs) + '</main>'
        '<footer><b>字段与口径</b><br>'
        '1. 「体验卡可读」= 接口 payingStatus=1（体验卡可免费读付费内容）；已排除 soldout=1 的下架书。<br>'
        '2. 推荐值 = newRating / 10（接口 0~1000 尺度，界面显示 93.0% 这种）；评价人数 = newRatingCount；阅读人数 = 书籍分享页 readingStat.readingCount（列表接口返回的不是累计口径，中位数仅 23，已改为逐本补抓）。<br>'
        '3. 字数来自书籍详情接口 totalWords，逐本补抓；未抓到的显示「—」。<br>'
        '4. 分类口径：大类与子类都直接取自平台书目元数据 category 字段（形如「历史-历史典籍」「文学-古典文学」），不是按抓取榜单命名；同一本书出现在哪个榜单不影响它的归类。<br>'
        '5. 三大榜单：神作榜 = 推荐值 ≥ 90% 且 累计阅读人数 ≥ 5000；神作潜力榜 = 推荐值 ≥ 90% 且 累计阅读人数 < 5000；好评如潮榜 = 85% ≤ 推荐值 < 90% 且 累计阅读人数 ≥ 1500。<br>'
        '6. 数据来自分类榜/子分类榜 Top 枚举（一级 300、经济理财/科学技术/哲学宗教/政治军事 480 + 子分类各 480），覆盖头部书目，不等于全库。<br>'
        '7. 体验卡是限时免费读付费内容，同一本书权益可能随时间变化，以抓取时间为准。<br>'
        '8. 列表已剔除无评分（评价人数 0）与推荐值 < 60% 的书；同一本书的不同版本（书名核心相似、作者关键词重合，忽略「（果麦经典）」这类括注与「[法]」国籍前缀）只保留评分最高的版本。</footer>'
        '<script>\n'
        'var tabs=[].slice.call(document.querySelectorAll(".tab"));\n'
        'var secs=[].slice.call(document.querySelectorAll(".cat"));\n'
        'function show(i){\n'
        '  tabs.forEach(function(t){t.classList.toggle("on",t.dataset.i===i)});\n'
        '  secs.forEach(function(s){s.classList.toggle("show",s.dataset.i===i)});\n'
        '  window.scrollTo({top:0,behavior:"smooth"});\n'
        '}\n'
        'tabs.forEach(function(t){t.addEventListener("click",function(){show(t.dataset.i)})});\n'
        'show("all");\n'
        '</script></body></html>')
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(head)
    print('HTML 已写出 %s（%d 本 / %d 类 / 榜单 %d / 字数覆盖 %d）'
          % (os.path.abspath(OUT), len(books), len(cat_order), len(RANKS), n_words), flush=True)


def main():
    os.chdir(WORK)
    payload = json.load(open(POOL, encoding='utf-8'))
    try:
        extra = json.load(open(EXTRA, encoding='utf-8'))
    except Exception:
        extra = {}
    try:
        read = json.load(open(READ, encoding='utf-8'))
    except Exception:
        read = {}
    build(payload, extra, read)


if __name__ == '__main__':
    main()
