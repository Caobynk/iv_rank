# -*- coding: utf-8 -*-
"""fetch_overview.py - 成交统计抓取（由 update_data.py 以子进程调用）

抓取 5 交易所最新交易日日行情到 data/*.json（缓存优先，缺失抓取）。
"""
import sys

OVERVIEW_DIR = r'D:\WorkBuddy\商品期权成交统计'
if OVERVIEW_DIR not in sys.path:
    sys.path.insert(0, OVERVIEW_DIR)

from data_aggregator import aggregate_all_exchanges


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else '20260820'
    try:
        result = aggregate_all_exchanges(date, days=5)
        s = result['summary']
        print(f"[overview] 最新 {result['end_date']} | {len(result['trading_days'])} 交易日 | "
              f"品种 {s['total_varieties']} | 期权日均量 {s['total_options_avg_volume']:,.0f}")
        return 0
    except Exception as e:
        print(f"[overview] 失败: {type(e).__name__}: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
