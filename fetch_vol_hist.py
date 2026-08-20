# -*- coding: utf-8 -*-
"""fetch_vol_hist.py - 历史波动率抓取（由 update_data.py 以子进程调用）

用 akshare 刷新所有已缓存品种的 OI 加权指数（force=True），写 .cache/*.csv。
"""
import os
import re
import sys

VOLHIST_DIR = r'D:\WorkBuddy\商品期货历史波动率估计'
if VOLHIST_DIR not in sys.path:
    sys.path.insert(0, VOLHIST_DIR)

from futures_data import get_volatility


def main():
    cache_dir = os.path.join(VOLHIST_DIR, '.cache')
    # 只处理纯品种代码缓存（排除 _YYYY 年份后缀变体，如 rb_2026.csv）
    codes = sorted(
        f.replace('.csv', '') for f in os.listdir(cache_dir)
        if f.endswith('.csv') and not re.search(r'_\d{4}\.csv$', f)
    )
    ok, fail = 0, 0
    for c in codes:
        try:
            r = get_volatility(c, window=30, force=True, start_year=None)
            print(f"[vol_hist] {c}: {r['points']} 点, end {r['end']}")
            ok += 1
        except Exception as e:
            print(f"[vol_hist] {c} 失败: {type(e).__name__}: {str(e)[:60]}")
            fail += 1
    print(f"[vol_hist] 完成: 成功 {ok} / 失败 {fail} / 共 {len(codes)}")
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
