# -*- coding: utf-8 -*-
"""补抓书目详情（字数等列表接口没有的字段）。

列表接口 bookInfo 不含字数，需逐本请求 /web/book/info；必须先访问首页，否则 wr_skey
未签发会返回「用户不存在」且 totalWords=0。可断点续跑：已成功的书不重复请求。

产出：_book_extra.json  {bookId: {ok, totalWords, isbn, centPrice, format, finished}}
"""
import json
import os
import sys
import time

import wrconfig
from playwright.sync_api import sync_playwright

BASE = 'https://weread.qq.com'
POOL = '_discover_pool.json'
OUT = '_book_extra.json'
SLEEP = float(os.environ.get('SLEEP', '0.2'))


def jload(p):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return {}


def jdump(obj, p):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, p)


def main():
    os.chdir(str(wrconfig.WORK))
    pool = json.load(open(POOL, encoding='utf-8'))
    ids = [b['bookId'] for b in pool['books']
           if b['rights'] == 'T' and b.get('soldout') != 1]
    out = jload(OUT)
    todo = [b for b in ids if not ((out.get(b) or {}).get('ok') and (out.get(b) or {}).get('totalWords'))]
    print('待抓 %d 本（已完成 %d）' % (len(todo), len(ids) - len(todo)), flush=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            wrconfig.PROFILE_DIR, **wrconfig.launch_kwargs(headless=True))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BASE + '/', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(1500)
        if not wrconfig.has_login(ctx):
            print('LOGIN_LOST：请先运行 python scripts/login.py 扫码登录', flush=True)
            return 2

        t0, n_ok, n_fail = time.time(), 0, 0
        for i, bid in enumerate(todo, 1):
            rec = {'ok': False}
            for _ in range(2):
                try:
                    j = ctx.request.get(BASE + '/web/book/info?bookId=' + bid,
                                        timeout=20000).json()
                    if not j.get('title'):
                        raise ValueError('errCode=%s %s' % (j.get('errCode'), j.get('errMsg')))
                    rec = {'ok': True,
                           'title': j.get('title'),
                           'totalWords': j.get('totalWords') or 0,
                           'centPrice': j.get('centPrice'),
                           'isbn': j.get('isbn'),
                           'format': j.get('format'),
                           'finished': j.get('finished')}
                    break
                except Exception as e:
                    rec = {'ok': False, 'err': str(e)[:80]}
                    time.sleep(0.8)
            out[bid] = rec
            n_ok += 1 if rec['ok'] else 0
            n_fail += 0 if rec['ok'] else 1
            if i % 50 == 0:
                jdump(out, OUT)
                el = time.time() - t0
                eta = (len(todo) - i) * el / i / 60
                print('  %d/%d 成功 %d 失败 %d %.2f 本/秒 剩余约 %.1f 分钟'
                      % (i, len(todo), n_ok, n_fail, i / el, eta), flush=True)
            time.sleep(SLEEP)

        jdump(out, OUT)
        ctx.close()
    print('完成 %d 本，失败 %d，用时 %.1f 分钟' % (n_ok, n_fail, (time.time() - t0) / 60), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
