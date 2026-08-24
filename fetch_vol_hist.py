# -*- coding: utf-8 -*-
"""fetch_vol_hist.py - 历史波动率数据准备（由 update_data.py 调用）

不再联网抓取：直接读取 D:\\WorkBuddy\\DataCenter\\Corr.xlsx（Wind 品种加权指数，
由源项目 corr_source 解析），取出各品种收盘价序列，写入 .cache/{code}.csv
（仅 close 列），供 build_site.py 的 build_vol_hist 计算波动率。

完全无网络依赖，彻底根治 akshare 抓取无超时导致的永久卡死。

品种清单沿用现有 .cache/*.csv（排除 _YYYY 年份后缀变体），与已部署静态页一致；
Excel 中无对应数据的品种保留旧缓存（不覆盖）。
"""
import os
import re
import sys
import datetime

VOLHIST_DIR = r'D:\WorkBuddy\商品期货历史波动率估计'
if VOLHIST_DIR not in sys.path:
    sys.path.insert(0, VOLHIST_DIR)

from varieties import get_variety                # noqa: E402
from corr_source import compute_index_from_corr  # noqa: E402


def main():
    cache_dir = os.path.join(VOLHIST_DIR, '.cache')
    codes = sorted(
        f.replace('.csv', '') for f in os.listdir(cache_dir)
        if f.endswith('.csv') and not re.search(r'_\d{4}\.csv$', f)
    )
    ok, skip = 0, 0
    for c in codes:
        try:
            variety = get_variety(c)
            if variety is None:
                print(f"[vol_hist] - {c} 不在品种表，跳过", flush=True)
                skip += 1
                continue
            # Excel 收盘价序列（date 索引，仅 close 列）
            idx = compute_index_from_corr(variety)
            if idx is None:
                print(f"[vol_hist] - {c} Excel 无数据，保留旧缓存", flush=True)
                skip += 1
                continue
            idx[['close']].to_csv(os.path.join(cache_dir, f'{c}.csv'))
            end = idx.index[-1].date()
            print(f"[vol_hist] + {c} ({variety['name']}): {len(idx)} 点, end {end}", flush=True)
            ok += 1
        except Exception as e:
            print(f"[vol_hist] {c} 失败: {type(e).__name__}: {str(e)[:80]}", flush=True)
            skip += 1
    print(f"[vol_hist] 完成: 更新 {ok} / 跳过 {skip} / 共 {len(codes)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
