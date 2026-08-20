# -*- coding: utf-8 -*-
"""fetch_oi_dist.py - 最痛点期权合约抓取（由 update_data.py 以子进程调用）

抓取 5 交易所期权合约到 cache/*.json（缓存优先，缺失抓取）。
"""
import sys

OIDIST_DIR = r'D:\WorkBuddy\商品期权成交持仓分布及最痛点位绘制'
if OIDIST_DIR not in sys.path:
    sys.path.insert(0, OIDIST_DIR)

from analyzer import fetch_exchange_options


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else '20260820'
    ok = {}
    fail = 0
    for ex in ['CZCE', 'SHFE', 'INE', 'GFEX', 'DCE']:
        try:
            d = fetch_exchange_options(ex, date)
            ok[ex] = len(d) if d else 0
            print(f"[oi_dist] {ex}: {ok[ex]} 品种")
        except Exception as e:
            print(f"[oi_dist] {ex} 失败: {type(e).__name__}: {str(e)[:80]}")
            fail += 1
    print(f"[oi_dist] 完成: {ok} | 失败 {fail}")
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
