# -*- coding: utf-8 -*-
"""发现层抓取：分类导航 + 榜单列表 → _discover_pool.json。

接口（均为服务端渲染/JSON，榜单元数据自带权益字段，无需逐本查详情）：
  1) GET /web/category/all                              → 一级分类导航
  2) GET /web/bookListInCategory/<id>?maxIndex=N[&rank=1] → 每页 20 本

权益判定：paid=1 永久可读；payingStatus=1 体验卡；2 付费会员卡；0 免费；其余归「其他」。
列表硬上限：maxIndex 0~460 可翻页，≥500 返回空 → 单列表最多 480 本。
重点分类再叠加子分类入口扩量。

用法：WEREAD_WORK=<数据目录> python fetch_pool.py
"""
import json
import os
import re
import sys
import time

import wrconfig
from playwright.sync_api import sync_playwright

BASE = 'https://weread.qq.com'
PER_CAT = int(os.environ.get('PER_CAT', '300'))
DEEP_LIMIT = int(os.environ.get('DEEP_LIMIT', '480'))
DEEP_CATS = tuple(x.strip() for x in
                  (os.environ.get('DEEP_CATS') or '1100000,1500000,600000,1200000').split(',')
                  if x.strip())
SLEEP = float(os.environ.get('SLEEP', '0.3'))
POOL = '_discover_pool.json'

RIGHTS = {'P': '永久可读', 'M': '付费会员卡可读', 'T': '体验卡可读', 'F': '免费', 'X': '其他付费模式'}

# 平台一级分类 ID 的展示顺序（未知 ID 追加在末尾）
CAT_ORDER = ['100000', '200000', '300000', '400000', '500000', '600000', '700000', '800000',
             '900000', '1000000', '1100000', '1200000', '1300000', '1400000', '1500000',
             '1600000', '1700000', '1800000', '1900001', '2000001', '2100000', '2400000']


def rights_of(bi):
    if bi.get('paid') == 1:
        return 'P'
    ps = bi.get('payingStatus')
    return {2: 'M', 1: 'T', 0: 'F'}.get(ps, 'X')


def price_of(bi):
    for v, scale in ((bi.get('price'), 1), (bi.get('centPrice'), 100), (bi.get('realPrice'), 100)):
        if isinstance(v, (int, float)) and v > 0:
            return round(float(v) / scale, 2)
    return None


def norm(e, cat_name, subcat=''):
    bi = e.get('bookInfo') or {}
    bid = str(bi.get('bookId') or '')
    if not bid:
        return None
    nr = bi.get('newRating')
    return {
        'bookId': bid, 'title': bi.get('title') or '', 'author': bi.get('author') or '',
        'category': bi.get('category') or '', 'discoverCat': cat_name, 'subCat': subcat,
        'rights': rights_of(bi), 'payingStatus': bi.get('payingStatus'), 'payType': bi.get('payType'),
        'price': price_of(bi), 'newRating': nr,
        'rating': round(nr / 10.0, 1) if isinstance(nr, (int, float)) and nr else None,
        'ratingCount': bi.get('newRatingCount') or bi.get('ratingCount'),
        'readingCount': e.get('readingCount'), 'soldout': bi.get('soldout'),
        'publishTime': bi.get('publishTime'), 'publisher': bi.get('publisher'),
        'intro': (bi.get('intro') or '')[:200], 'deepLink': bi.get('deepLink') or '',
    }


def discover_cats(ctx):
    """从 /web/category/all 抓一级分类导航，并追加神作榜/神作潜力榜。"""
    html = ctx.request.get(BASE + '/web/category/all', timeout=30000).text()
    pairs = re.findall(r'href="(/web/category/([0-9a-z_]+))"[^>]*>(?:<[^>]+>)*([^<]{2,14})', html)
    name_of = {}
    for href, cid, nm in pairs:
        nm = nm.strip()
        if cid.isdigit() and nm and cid not in name_of:
            name_of[cid] = nm
    cats = [(cid, name_of[cid], False) for cid in CAT_ORDER if cid in name_of]
    cats += [(cid, nm, False) for cid, nm in name_of.items()
             if cid not in CAT_ORDER]
    # 高价值榜单（rank=1）
    for cid, nm in (('newrating_publish', '神作榜·出版'),
                    ('newrating_potential_publish', '神作潜力榜·出版')):
        cats.append((cid, nm, True))
    return cats


def discover_subcats(ctx, cid):
    """从 /web/category/<cid> 的 SSR 里提取子分类清单 [(subId, 名称)]。"""
    html = ctx.request.get('%s/web/category/%s' % (BASE, cid), timeout=30000).text()
    pairs = re.findall(
        r'"categoryId":%s,"subCategoryId":(\d+),"categoryType":0,"title":"([^"]{2,24})"' % cid, html)
    return list(dict.fromkeys(pairs))


def crawl_list(ctx, list_id, cname, limit, is_rank, pool, subcat=''):
    """按 maxIndex 翻一个列表直到 limit。

    空响应原地重试（不推进 maxIndex），连续 3 次才判定到底；
    请求异常也原地重试，连续 4 次失败才放弃这个列表。
    """
    idx, n_new, fails, empty = 0, 0, 0, 0
    while idx < limit:
        url = '%s/web/bookListInCategory/%s?maxIndex=%d%s' % (
            BASE, list_id, idx, '&rank=1' if is_rank else '')
        try:
            j = ctx.request.get(url, timeout=25000).json()
        except Exception as e:
            fails += 1
            print('    %s maxIndex=%d 请求失败 %s（第 %d 次）' % (list_id, idx, str(e)[:60], fails),
                  flush=True)
            if fails >= 4:
                break
            time.sleep(1.2)
            continue
        books = j.get('books') or []
        if not books:
            empty += 1
            if empty >= 3:
                break
            time.sleep(0.8)
            continue
        fails, empty = 0, 0
        for e in books:
            rec = norm(e, cname, subcat)
            if rec and rec['bookId'] not in pool:
                pool[rec['bookId']] = rec
                n_new += 1
        idx += 20
        time.sleep(SLEEP)
    return n_new


def main():
    os.makedirs(str(wrconfig.WORK), exist_ok=True)
    os.chdir(str(wrconfig.WORK))
    pool, stat = {}, []
    t_start = time.time()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            wrconfig.PROFILE_DIR, **wrconfig.launch_kwargs(headless=True))
        if not wrconfig.has_login(ctx):
            print('LOGIN_LOST：请先运行 python scripts/login.py 扫码登录', flush=True)
            return 2
        print('登录态正常', flush=True)

        cats = discover_cats(ctx)
        print('发现分类 %d 个：%s' % (len(cats), '、'.join(c[1] for c in cats)), flush=True)

        for cid, cname, is_rank in cats:
            t0 = time.time()
            limit = DEEP_LIMIT if cid in DEEP_CATS else PER_CAT
            n_cat = crawl_list(ctx, cid, cname, limit, is_rank, pool)
            stat.append({'id': cid, 'name': cname, 'got': n_cat, 'sec': round(time.time() - t0, 1)})
            print('  [%-26s] 新增 %-4d 累计 %-5d %.1fs'
                  % (cid, n_cat, len(pool), time.time() - t0), flush=True)

            if cid not in DEEP_CATS:
                continue
            subs = discover_subcats(ctx, cid)
            print('    └ %s 有 %d 个子分类：%s'
                  % (cname, len(subs), '、'.join(t for _, t in subs)), flush=True)
            for sid, title in subs:
                t1 = time.time()
                n_sub = crawl_list(ctx, sid, cname, DEEP_LIMIT, False, pool, subcat=title)
                stat.append({'id': sid, 'name': '%s·%s' % (cname, title), 'got': n_sub,
                             'sec': round(time.time() - t1, 1), 'parent': cid})
                print('      [%-8s] %-10s 新增 %-4d 累计 %-5d %.1fs'
                      % (sid, title, n_sub, len(pool), time.time() - t1), flush=True)

        ctx.close()

    payload = {'fetchedAt': int(time.time()), 'perCat': PER_CAT, 'deepLimit': DEEP_LIMIT,
               'deepCats': list(DEEP_CATS), 'cats': stat, 'books': list(pool.values())}
    with open(POOL, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    dist = {}
    for v in pool.values():
        dist[v['rights']] = dist.get(v['rights'], 0) + 1
    print('\n候选去重 %d 本（用时 %.1f 分钟）权益分布: %s'
          % (len(pool), (time.time() - t_start) / 60, dist), flush=True)
    print('已写出 %s' % os.path.abspath(POOL), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
