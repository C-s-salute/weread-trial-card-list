# -*- coding: utf-8 -*-
"""串联整条流程：抓取 → 补抓 → 生成 HTML/Excel。

用法：
    python run_pipeline.py            # 全量：登录态需已就绪
    python run_pipeline.py --reuse    # 跳过抓取，直接用已有缓存重出报告
    python run_pipeline.py --skip-extra   # 跳过字数补抓（用已有缓存）

环境变量同 SKILL.md（WEREAD_WORK / WEREAD_PROFILE / PER_CAT / DEEP_LIMIT ...）。
"""
import os
import subprocess
import sys

import wrconfig

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = str(wrconfig.WORK)
POOL = os.path.join(WORK, '_discover_pool.json')


def run(name):
    path = os.path.join(HERE, name)
    print('\n=== %s ===' % name, flush=True)
    r = subprocess.run([sys.executable, path], env=dict(os.environ, WEREAD_WORK=WORK))
    if r.returncode != 0:
        print('%s 退出码 %d' % (name, r.returncode), flush=True)
        sys.exit(r.returncode)


def main(argv):
    reuse = '--reuse' in argv
    if not reuse:
        run('fetch_pool.py')
        if '--skip-extra' not in argv:
            run('fetch_extra.py')
        run('fetch_readcount.py')
    run('build_html.py')
    run('build_excel.py')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
