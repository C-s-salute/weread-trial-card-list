# -*- coding: utf-8 -*-
"""微信读书扫码登录：登录态写入持久化 profile，后续抓取全部复用。

用法：
    python login.py                # 打开有头浏览器，用微信扫码；成功后自动退出
    python login.py --timeout 300  # 自定义等待秒数

登录态只保存在 profile 目录（默认 ~/.weread-trial-card-list/profile），
不落任何明文 cookie / token 文件。
"""
import sys
import time

from playwright.sync_api import sync_playwright

import wrconfig

BASE = 'https://weread.qq.com'


def wait_login(page, ctx, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if wrconfig.has_login(ctx):
            return True
        page.wait_for_timeout(1500)
    return False


def main(argv):
    timeout = 300
    if '--timeout' in argv:
        timeout = int(argv[argv.index('--timeout') + 1])

    wrconfig.ensure_profile()
    print('profile:', wrconfig.PROFILE_DIR)
    print('browser:', wrconfig.channel() or 'chromium(bundled)')

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            wrconfig.PROFILE_DIR,
            **wrconfig.launch_kwargs(headless=False, viewport={'width': 1180, 'height': 860}))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BASE + '/', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(1500)

        if wrconfig.has_login(ctx):
            print('已登录，无需扫码')
            ctx.close()
            return 0

        print('请在打开的浏览器窗口里用微信扫码登录（%d 秒内有效）' % timeout)
        ok = wait_login(page, ctx, timeout)
        ctx.close()

    if ok:
        print('登录成功，profile 已保存')
        return 0
    print('登录超时：未检测到 wr_vid cookie，请重试')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
