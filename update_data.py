# -*- coding: utf-8 -*-
"""
update_data.py - 商品期权信息汇总面板 · 数据抓取更新脚本

在 build_site.py 之前运行：把 6 个子服务的数据抓取/更新到最新交易日。
每个子服务用其自身 venv + 独立脚本执行（依赖隔离，避免 varieties.py 等模块名冲突）。

抓取策略（对应各子服务数据源）：
  1. overview 成交统计    - 5 交易所日行情（requests + Playwright 反爬），写 data/*.json
  2. oi_dist 最痛点       - 5 交易所期权合约（requests + Playwright），写 cache/*.json
  3. vol_hist 波动率     - akshare 期货日线 + OI 加权指数（force 刷新），写 .cache/*.csv
  4. iv_rank  IV 分位    - 数据源为主人维护的 Excel（无需抓取，直接复用最新）
  5. pcr     PCR 跟踪     - 5 交易所期权 PCR（增量回补 + 重建三表），写 data/tables/*.csv
  6. gex     GEX 分析     - 交易所行情（requests + Playwright），写 market_cache/*.json

用法：venv/Scripts/python.exe update_data.py
由 update.bat 在 build_site.py 之前调用。
"""
import datetime
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 各子服务项目根目录 + venv python（固定，与 config.json 一致）
PROJECTS = {
    'overview': {
        'script': 'fetch_overview.py',
        'venv': r'D:\WorkBuddy\商品期权成交统计\.venv\Scripts\python.exe',
    },
    'oi_dist': {
        'script': 'fetch_oi_dist.py',
        'venv': r'D:\WorkBuddy\商品期权成交持仓分布及最痛点位绘制\.venv\Scripts\python.exe',
    },
    'vol_hist': {
        'script': 'fetch_vol_hist.py',
        'venv': r'D:\WorkBuddy\商品期货历史波动率估计\.venv\Scripts\python.exe',
    },
    'iv_rank': {
        'script': None,  # Excel 由主人维护，无需抓取
        'venv': r'D:\WorkBuddy\IV_Rank\venv\Scripts\python.exe',
    },
    'pcr': {
        'script': 'fetch_pcr.py',
        'venv': r'D:\WorkBuddy\商品期权PCR跟踪\.venv\Scripts\python.exe',
    },
    'gex': {
        'script': 'fetch_gex_market.py',
        'venv': r'D:\WorkBuddy\GEX观察\.venv\Scripts\python.exe',
    },
}


def run_step(name, date, timeout=900):
    """在指定项目 venv 中执行抓取脚本。"""
    cfg = PROJECTS[name]
    if not cfg['script']:
        print(f'\n[{name}] 数据源为主人维护，跳过抓取')
        return True
    script = os.path.join(BASE_DIR, cfg['script'])
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    cmd = [cfg['venv'], '-u', script, date]
    print(f'\n{"="*56}\n▶ [{name}] {cfg["script"]}\n{"="*56}', flush=True)
    try:
        # 实时流式输出：逐行转发子进程 stdout/stderr，避免长时间无反馈
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=env, cwd=BASE_DIR, encoding='utf-8', errors='replace',
                             bufsize=1, text=True)
        lines = []
        while True:
            line = p.stdout.readline()
            if not line:
                break
            line = line.rstrip('\n')
            lines.append(line)
            print(f'  {line}', flush=True)
        p.wait(timeout=timeout)
        if p.returncode != 0:
            print(f'[ERROR] {name} 退出码 {p.returncode}')
            return False
        return True
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
        print(f'[ERROR] {name} 超时（>{timeout}s）')
        return False
    except FileNotFoundError as e:
        print(f'[ERROR] {name} venv 不存在: {e}')
        return False


def latest_trade_date():
    """计算目标交易日：今天（若为交易日）否则最近工作日。"""
    d = datetime.date.today()
    while d.weekday() >= 5:  # 周末回退
        d -= datetime.timedelta(days=1)
    return d.strftime('%Y%m%d')


def main():
    date = latest_trade_date()
    print(f'=== 商品期权信息汇总面板 · 数据抓取更新 ===')
    print(f'目标交易日: {date}')

    results = {}
    results['overview'] = run_step('overview', date)
    results['oi_dist'] = run_step('oi_dist', date)
    results['vol_hist'] = run_step('vol_hist', date)
    results['iv_rank'] = run_step('iv_rank', date)
    results['pcr'] = run_step('pcr', date)
    results['gex'] = run_step('gex', date)

    print('\n' + '=' * 56)
    print('=== 数据更新汇总 ===')
    for k, v in results.items():
        print(f'  {"✅" if v else "❌"} {k}')
    if not all(results.values()):
        print('⚠ 部分子服务更新失败，请检查上方日志（可继续构建，将使用已有缓存）')
        sys.exit(1)
    print('全部更新成功')


if __name__ == '__main__':
    main()
