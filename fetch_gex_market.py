# -*- coding: utf-8 -*-
"""fetch_gex_market.py - GEX 行情抓取（由 update_data.py 以子进程调用）

抓取全部品种的期权行情到 market_cache/*.json（缓存优先，缺失抓取）。
覆盖 5 交易所全部期权品种，确保 GEX 构建时所有品种都有行情缓存。

注意：DCE 品种每个品种必须用独立进程抓取（同进程多次启动 Playwright
会触发 'PlaywrightContextManager has no attribute _playwright' 崩溃）。
本脚本支持 --dce-one <code> 子进程模式。
"""
import os
import subprocess
import sys

GEX_DIR = r'D:\WorkBuddy\GEX观察'
OIDIST_DIR = r'D:\WorkBuddy\商品期权成交持仓分布及最痛点位绘制'
for d in (GEX_DIR, OIDIST_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import commodity_market
from varieties import get_varieties_grouped


def _fetch_one(exchange, code, date):
    """抓取单个品种（含 DCE），返回 (und_n, opts_n)。"""
    und, opts = commodity_market.get_market(exchange, code, date)
    return len(und), len(opts)


def fetch_dce_one(date):
    """子进程模式：仅抓取单个 DCE 品种。调用：script <date> --dce-one <code>"""
    code = sys.argv[3] if len(sys.argv) > 3 else ''
    if not code:
        print('[gex] 缺少 DCE 品种代码参数')
        return 1
    try:
        n_und, n_opts = _fetch_one('DCE', code, date)
        print(f'[gex] DCE/{code}: und {n_und} opts {n_opts}')
        return 0
    except Exception as e:
        print(f'[gex] DCE/{code} 失败: {type(e).__name__}: {str(e)[:80]}')
        return 1


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else '20260820'
    if len(sys.argv) > 2 and sys.argv[2] == '--dce-one':
        return fetch_dce_one(date)

    groups = get_varieties_grouped()
    venv = sys.executable
    script = os.path.abspath(__file__)
    ok, fail = 0, 0
    fails = []
    for g in groups:
        ex = g['exchange']
        for v in g['varieties']:
            code = v['code']
            try:
                if ex == 'DCE':
                    # DCE 必须独立进程抓取，避免 Playwright 上下文崩溃
                    r = subprocess.run([venv, '-u', script, date, '--dce-one', code],
                                       capture_output=True, text=True, timeout=180,
                                       encoding='utf-8', errors='replace')
                    line = (r.stdout or '').strip().splitlines()[-1] if (r.stdout or '').strip() else ''
                    print(f'  {line}  (rc={r.returncode})')
                    if r.returncode == 0:
                        ok += 1
                    else:
                        fail += 1
                        fails.append(f'DCE/{code}')
                else:
                    n_und, n_opts = _fetch_one(ex, code, date)
                    print(f'[gex] {ex}/{code}: und {n_und} opts {n_opts}')
                    ok += 1
            except Exception as e:
                print(f'[gex] {ex}/{code} 失败: {type(e).__name__}: {str(e)[:60]}')
                fail += 1
                fails.append(f'{ex}/{code}')
    print(f'[gex] 完成: 成功 {ok} / 失败 {fail} / 共 {sum(len(g["varieties"]) for g in groups)}')
    if fails:
        print(f'[gex] 失败清单: {fails}')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
