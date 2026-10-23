# -*- coding: utf-8 -*-
"""补抓「累计阅读人数」。

列表接口里的 readingCount 中位数只有 23，不是累计口径；真正的累计阅读人数在书籍
分享页 /book-detail?type=1&v=<encodeId> 的 readingStat.readingCount（公开 SSR 页）。

产出：_book_read.json {bookId: {ok, readingCount}}，可断点续跑。
"""
import json
import os
import re
import sys
import time

import wrconfig
from playwright.sync_api import sync_playwright

POOL = '_discover_pool.json'
OUT = '_book_read.json'
SLEEP = float(os.environ.get('SLEEP', '0.15'))
PAT = re.compile(r'readingStat:\{readingCount:(\d+)\}')


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
    targets = [(b['bookId'], b.get('deepLink') or '') for b in pool['books']
               if b['rights'] == 'T' and b.get('soldout') != 1 and b.get('deepLink')]
    out = jload(OUT)
    todo = [(bid, u) for bid, u in targets if not (out.get(bid) or {}).get('ok')]
    print('待抓 %d 本（已完成 %d）' % (len(todo), len(targets) - len(todo)), flush=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            wrconfig.PROFILE_DIR, **wrconfig.launch_kwargs(headless=True))
        t0, n_ok, n_fail = time.time(), 0, 0
        for i, (bid, url) in enumerate(todo, 1):
            rec = {'ok': False}
            for _ in range(2):
                try:
                    html = ctx.request.get(url, timeout=30000).text()
                    m = PAT.search(html) or re.search(r'"readingCount":(\d+)', html)
                    if not m:
                        raise ValueError('未匹配到 readingCount')
                    rec = {'ok': True, 'readingCount': int(m.group(1))}
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
                print('  %d/%d 成功 %d 失败 %d %.2f 本/秒 剩余约 %.1f 分钟'
                      % (i, len(todo), n_ok, n_fail, i / el,
                         (len(todo) - i) * el / i / 60), flush=True)
            time.sleep(SLEEP)

        jdump(out, OUT)
        ctx.close()
    print('完成 %d 本，失败 %d，用时 %.1f 分钟' % (n_ok, n_fail, (time.time() - t0) / 60), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
