# -*- coding: utf-8 -*-
"""fetch_pcr.py - PCR 跟踪抓取（由 update_data.py 以子进程调用）

增量回补 5 交易所期权 PCR 数据 + 重建三表（data/tables/*.csv）。
"""
import sys
from datetime import datetime, timedelta

PCR_DIR = r'D:\WorkBuddy\商品期权PCR跟踪'
if PCR_DIR not in sys.path:
    sys.path.insert(0, PCR_DIR)

from pipeline.backfill import last_complete_date, run_backfill, dce_backfill, gfex_backfill
from pipeline.build_tables import build_tables


def main():
    last = last_complete_date()
    print(f'[pcr] 当前完整日期: {last}')
    start = (datetime.strptime(last, '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d') if last else None
    end = datetime.now().strftime('%Y%m%d')
    fail = 0
    if start and start > end:
        print(f'[pcr] 数据已最新（{last}），无需回补')
    else:
        print(f'[pcr] 增量区间: {start} -> {end}')
        s = run_backfill(start_date=start, end_date=end, log=lambda m: None)
        print(f'[pcr] HTTP 回补: {s}')
        for name, fn in [('DCE', dce_backfill), ('GFEX', gfex_backfill)]:
            try:
                fn(start_date=start, end_date=end, log=lambda m: None)
                print(f'[pcr] {name} 回补完成')
            except Exception as e:
                print(f'[pcr] {name} 回补跳过: {type(e).__name__}')
                fail += 1
    info = build_tables()
    print(f'[pcr] 三表重建: {info}')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
