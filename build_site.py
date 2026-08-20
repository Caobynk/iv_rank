# -*- coding: utf-8 -*-
"""
build_site.py - 商品期权信息汇总面板 · 静态站点构建脚本

仿照 IV_Rank 的 build_data.py 模式：把各子服务本地缓存数据转换为静态 JSON，
输出到 static/ 目录（Cloudflare Pages 输出目录），配合前端静态页实现纯静态部署。

生成内容：
  static/sub/overview/data.json        - 商品期权成交统计（最新交易日聚合）
  static/sub/oi_dist/varieties.json    - 品种分组
  static/sub/oi_dist/data/<code>.json  - 每品种最新交易日分布/最痛点
  static/sub/vol_hist/varieties.json   - 品种分组
  static/sub/vol_hist/data/<code>.json - 每品种历史波动率（默认 window=30, startYear=auto）
  static/sub/iv_rank/api/*.json        - IV 分位（复用 IV_Rank 纯函数）
  static/sub/pcr/varieties.json        - PCR 品种列表
  static/sub/pcr/data/<key>.json       - 每品种 PCR 全量
  static/sub/gex/varieties.json        - GEX 品种分组
  static/sub/gex/data/<code>.json      - 每品种最新交易日 GEX
  static/corr/                         - 相关性静态页（原样复制）
  static/site_info.json                - 各子页数据日期汇总

运行环境：需 pandas/numpy/openpyxl/requests（复用 GEX观察/.venv）。
用法：venv/Scripts/python.exe build_site.py
"""
import json
import os
import shutil
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
SUB_DIR = os.path.join(STATIC_DIR, 'sub')

# 各子服务项目根目录（数据源）
P_OVERVIEW = r'D:\WorkBuddy\商品期权成交统计'
P_OIDIST = r'D:\WorkBuddy\商品期权成交持仓分布及最痛点位绘制'
P_VOLHIST = r'D:\WorkBuddy\商品期货历史波动率估计'
P_IVRANK = r'D:\WorkBuddy\IV_Rank'
P_PCR = r'D:\WorkBuddy\商品期权PCR跟踪'
P_GEX = r'D:\WorkBuddy\GEX观察'
P_CORR = r'D:\WorkBuddy\商品行情与波动率相关性'

LATEST_DATE = '20260818'  # 各子服务缓存的最新共同交易日（构建时从缓存探测，见下方）

def makedirs(p):
    os.makedirs(p, exist_ok=True)


def detect_latest_date():
    """从各子服务缓存目录探测最新共同交易日，避免硬编码过期。"""
    dates = []
    # 成交统计缓存 data/{ex}_{YYYYMMDD}.json
    d = os.path.join(P_OVERVIEW, 'data')
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith('.json') and '_' in f:
                ds = f.rsplit('_', 1)[1].replace('.json', '')
                if len(ds) == 8 and ds.isdigit():
                    dates.append(ds)
    # 最痛点缓存 cache/{ex}_{YYYYMMDD}.json
    d = os.path.join(P_OIDIST, 'cache')
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith('.json') and '_' in f:
                ds = f.rsplit('_', 1)[1].replace('.json', '')
                if len(ds) == 8 and ds.isdigit():
                    dates.append(ds)
    if dates:
        return max(dates)
    return LATEST_DATE


# ================= 1. overview 成交统计 =================
def build_overview(latest):
    """从成交统计本地缓存 data/*.json 聚合最新交易日数据（不联网）。"""
    out = os.path.join(SUB_DIR, 'overview')
    makedirs(out)
    cache_dir = os.path.join(P_OVERVIEW, 'data')
    if not os.path.isdir(cache_dir):
        print('[overview] 跳过：缓存目录不存在', cache_dir)
        return

    # 文件名前缀小写（dce_/czce_/...），统一转大写与交易所代码对齐
    _EX_ALIAS = {'dce': 'DCE', 'czce': 'CZCE', 'shfe': 'SHFE', 'ine': 'INE', 'gfex': 'GFEX'}
    day_files = {}  # date -> {ex: path}
    for f in os.listdir(cache_dir):
        if not f.endswith('.json') or '_' not in f:
            continue
        ex, ds = f.split('_', 1)
        ds = ds.replace('.json', '')
        if len(ds) != 8 or not ds.isdigit():
            continue
        ex = _EX_ALIAS.get(ex.lower(), ex.upper())
        day_files.setdefault(ds, {})[ex] = os.path.join(cache_dir, f)

    # 找最近 5 个交易日（至少 3 个交易所覆盖的日期，按日期降序）
    sorted_days = sorted(day_files.keys(), reverse=True)
    trading_days = []
    for ds in sorted_days:
        if len(day_files[ds]) >= 3:
            trading_days.append(ds)
        if len(trading_days) >= 5:
            break
    if not trading_days:
        print('[overview] 跳过：无足够交易日缓存')
        return

    # 聚合逻辑（与 data_aggregator.aggregate_all_exchanges 一致，只读缓存）
    exchanges = ['DCE', 'CZCE', 'SHFE', 'INE', 'GFEX']
    ex_names = {
        'DCE': 'DCE 大商所', 'CZCE': 'CZCE 郑商所', 'SHFE': 'SHFE 上期所',
        'INE': 'INE 上期能源', 'GFEX': 'GFEX 广期所',
    }
    ex_short = {'DCE': 'DCE', 'CZCE': 'CZCE', 'SHFE': 'SHFE', 'INE': 'INE', 'GFEX': 'GFEX'}

    def load_day(ex, ds):
        p = day_files.get(ds, {}).get(ex)
        if not p or not os.path.exists(p):
            return None
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    exchanges_result = {}
    all_varieties = []
    totals = {'fut_vol': 0.0, 'opt_vol': 0.0, 'fut_oi': 0.0, 'opt_oi': 0.0}

    for ex in exchanges:
        ex_data = []
        for ds in trading_days:
            d = load_day(ex, ds)
            if d is not None:
                ex_data.append(d)
        if not ex_data:
            continue
        # 品种聚合
        var_map = {}
        for day in ex_data:
            for item in day.get('data', []):
                code = item.get('variety_code')
                if not code:
                    continue
                v = var_map.setdefault(code, {
                    'variety_code': code,
                    'variety_name': item.get('variety_name', ''),
                    'exchange': ex,
                    'exchange_name': ex_names.get(ex, ex),
                    'futures_total_volume': 0, 'options_total_volume': 0,
                    'futures_total_turnover': 0.0, 'options_total_turnover': 0.0,
                    'futures_total_open_interest': 0, 'options_total_open_interest': 0,
                    'days': 0,
                })
                v['futures_total_volume'] += item.get('futures_volume', 0)
                v['options_total_volume'] += item.get('options_volume', 0)
                v['futures_total_turnover'] += item.get('futures_turnover', 0.0)
                v['options_total_turnover'] += item.get('options_turnover', 0.0)
                v['futures_total_open_interest'] += item.get('futures_open_interest', 0)
                v['options_total_open_interest'] += item.get('options_open_interest', 0)
                v['days'] += 1

        varieties = []
        for code, v in var_map.items():
            days = v['days'] or 1
            avg_fut = v['futures_total_volume'] / days
            avg_opt = v['options_total_volume'] / days
            avg_fut_oi = v['futures_total_open_interest'] / days
            avg_opt_oi = v['options_total_open_interest'] / days
            varieties.append({
                'variety_code': code,
                'variety_name': v['variety_name'],
                'exchange': ex,
                'exchange_name': ex_names.get(ex, ex),
                'futures_avg_volume': round(avg_fut, 2),
                'options_avg_volume': round(avg_opt, 2),
                'futures_avg_turnover': round(v['futures_total_turnover'] / days, 2),
                'options_avg_turnover': round(v['options_total_turnover'] / days, 2),
                'futures_avg_open_interest': round(avg_fut_oi, 2),
                'options_avg_open_interest': round(avg_opt_oi, 2),
                'options_to_futures_ratio': round(avg_opt / avg_fut, 4) if avg_fut > 0 else 0,
                'options_to_futures_ratio_pct': round(avg_opt / avg_fut * 100, 2) if avg_fut > 0 else 0,
                'options_oi_to_futures_ratio': round(avg_opt_oi / avg_fut_oi, 4) if avg_fut_oi > 0 else 0,
                'options_oi_to_futures_ratio_pct': round(avg_opt_oi / avg_fut_oi * 100, 2) if avg_fut_oi > 0 else 0,
                'days': days,
            })
        varieties.sort(key=lambda x: x['options_avg_volume'], reverse=True)

        ex_agg = {
            'fut_vol': sum(v['futures_avg_volume'] for v in varieties),
            'opt_vol': sum(v['options_avg_volume'] for v in varieties),
            'fut_oi': sum(v['futures_avg_open_interest'] for v in varieties),
            'opt_oi': sum(v['options_avg_open_interest'] for v in varieties),
        }
        exchanges_result[ex] = {
            'exchange': ex,
            'exchange_name': ex_names.get(ex, ex),
            'short': ex_short.get(ex, ex),
            'variety_count': len(varieties),
            'total_futures_avg_volume': round(ex_agg['fut_vol'], 2),
            'total_options_avg_volume': round(ex_agg['opt_vol'], 2),
            'ratio_pct': round(ex_agg['opt_vol'] / ex_agg['fut_vol'] * 100, 2) if ex_agg['fut_vol'] > 0 else 0,
            'total_futures_avg_open_interest': round(ex_agg['fut_oi'], 2),
            'total_options_avg_open_interest': round(ex_agg['opt_oi'], 2),
            'oi_ratio_pct': round(ex_agg['opt_oi'] / ex_agg['fut_oi'] * 100, 2) if ex_agg['fut_oi'] > 0 else 0,
            'varieties': varieties,
        }
        for k in totals:
            totals[k] += ex_agg[k]
        all_varieties.extend(varieties)

    all_varieties.sort(key=lambda x: x['options_avg_volume'], reverse=True)
    all_varieties_by_oi = sorted(all_varieties, key=lambda x: x['options_avg_open_interest'], reverse=True)

    data = {
        'end_date': trading_days[0],
        'trading_days': trading_days,
        'days_count': len(trading_days),
        'exchanges': exchanges_result,
        'summary': {
            'total_futures_avg_volume': round(totals['fut_vol'], 2),
            'total_options_avg_volume': round(totals['opt_vol'], 2),
            'total_varieties': len(all_varieties),
            'overall_ratio_pct': round(totals['opt_vol'] / totals['fut_vol'] * 100, 2) if totals['fut_vol'] > 0 else 0,
            'total_futures_avg_open_interest': round(totals['fut_oi'], 2),
            'total_options_avg_open_interest': round(totals['opt_oi'], 2),
            'overall_oi_ratio_pct': round(totals['opt_oi'] / totals['fut_oi'] * 100, 2) if totals['fut_oi'] > 0 else 0,
        },
        'all_varieties': all_varieties,
        'all_varieties_by_oi': all_varieties_by_oi,
    }
    payload = {'success': True, 'data': data}
    with open(os.path.join(out, 'data.json'), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"[overview] 生成 data.json：{len(all_varieties)} 品种，{len(trading_days)} 个交易日，最新 {trading_days[0]}")


# ================= 2. oi_dist 成交持仓分布/最痛点 =================
def build_oi_dist(latest):
    """从 cache/{ex}_{date}.json 为每个品种生成最新交易日分布数据。"""
    out = os.path.join(SUB_DIR, 'oi_dist')
    data_dir = os.path.join(out, 'data')
    makedirs(data_dir)
    if P_OIDIST not in sys.path:
        sys.path.insert(0, P_OIDIST)
    try:
        from analyzer import analyze_variety
        from varieties import get_varieties_grouped
    except Exception as e:
        print('[oi_dist] 跳过：import 失败', e)
        return

    # varieties.json
    groups = get_varieties_grouped()
    with open(os.path.join(out, 'varieties.json'), 'w', encoding='utf-8') as f:
        json.dump({'success': True, 'groups': groups}, f, ensure_ascii=False)

    # 每品种数据
    ok, fail = 0, 0
    for g in groups:
        for v in g['varieties']:
            code = v['code']
            try:
                r = analyze_variety(code, latest)
                if r.get('success'):
                    with open(os.path.join(data_dir, f'{code}.json'), 'w', encoding='utf-8') as f:
                        json.dump(r, f, ensure_ascii=False)
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                fail += 1
    print(f"[oi_dist] 生成 {ok} 个品种（失败 {fail}），交易日 {latest}")


# ================= 3. vol_hist 历史波动率 =================
def build_vol_hist(latest):
    """从 .cache/{code}.csv 计算默认参数（window=30, startYear=auto）波动率。"""
    out = os.path.join(SUB_DIR, 'vol_hist')
    data_dir = os.path.join(out, 'data')
    makedirs(data_dir)
    # 用 importlib 按文件路径定向加载，避免 varieties.py 模块名跨项目冲突
    try:
        import importlib.util
        import numpy as np  # noqa: F401
        import pandas as pd

        def _load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            return mod

        _vol = _load('volh_volatility', os.path.join(P_VOLHIST, 'volatility.py'))
        _var = _load('volh_varieties', os.path.join(P_VOLHIST, 'varieties.py'))
        compute_all = _vol.compute_all
        ANNUALIZATION = _vol.ANNUALIZATION
        get_varieties_grouped = _var.get_varieties_grouped
        get_variety = _var.get_variety
    except Exception as e:
        print('[vol_hist] 跳过：import 失败', e)
        return

    cache_dir = os.path.join(P_VOLHIST, '.cache')
    if not os.path.isdir(cache_dir):
        print('[vol_hist] 跳过：缓存目录不存在')
        return

    # 有缓存的品种
    codes = [f.replace('.csv', '') for f in os.listdir(cache_dir) if f.endswith('.csv')]

    # varieties.json（只列有缓存的品种，避免前端选到无数据项）
    all_groups = get_varieties_grouped()
    groups_out = []
    for g in all_groups:
        items = [it for it in g['items'] if it['code'] in codes]
        if items:
            groups_out.append({'exchange': g['exchange'], 'exchange_name': g['exchange_name'], 'items': items})
    with open(os.path.join(out, 'varieties.json'), 'w', encoding='utf-8') as f:
        json.dump(groups_out, f, ensure_ascii=False)

    ok, fail = 0, 0
    for code in codes:
        csv_path = os.path.join(cache_dir, f'{code}.csv')
        try:
            idx = pd.read_csv(csv_path, parse_dates=['date'], index_col='date')
            if idx.empty:
                fail += 1
                continue
            vol = compute_all(
                {'open': idx['open'], 'high': idx['high'], 'low': idx['low'], 'close': idx['close']},
                window=30, ann=ANNUALIZATION,
            )
            dates = [d.strftime('%Y-%m-%d') for d in idx.index]
            variety = get_variety(code)
            result = {
                'symbol': code,
                'name': variety['name'] if variety else code,
                'exchange': variety['exchange'] if variety else '',
                'category': variety['category'] if variety else '',
                'window': 30,
                'annualization': ANNUALIZATION,
                'start_year': 'auto',
                'dates': dates,
                'price': [None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v) for v in idx['close'].tolist()],
                'vol': {k: [None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v) for v in arr.tolist()] for k, arr in vol.items()},
                'points': len(dates),
                'start': dates[0] if dates else None,
                'end': dates[-1] if dates else None,
            }
            with open(os.path.join(data_dir, f'{code}.json'), 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False)
            ok += 1
        except Exception as e:
            fail += 1
    print(f"[vol_hist] 生成 {ok} 个品种（失败 {fail}），window=30")


# ================= 4. iv_rank IV 分位（复用 IV_Rank） =================
def build_iv_rank(latest):
    """复用 IV_Rank server 纯函数生成 api/*.json（与 IV_Rank build_data.py 同源）。"""
    out = os.path.join(SUB_DIR, 'iv_rank')
    api_dir = os.path.join(out, 'api')
    makedirs(api_dir)
    if P_IVRANK not in sys.path:
        sys.path.insert(0, P_IVRANK)
    try:
        import server as ivserver
    except Exception as e:
        print('[iv_rank] 跳过：import 失败', e)
        return

    build_days = 500
    overview = ivserver.get_overview(build_days)
    with open(os.path.join(api_dir, 'overview.json'), 'w', encoding='utf-8') as f:
        json.dump({'data': overview, 'count': len(overview)}, f, ensure_ascii=False)

    for item in overview:
        code = item['code']
        detail = ivserver.get_detail(code, build_days)
        if detail:
            with open(os.path.join(api_dir, f'detail_{code}.json'), 'w', encoding='utf-8') as f:
                json.dump(detail, f, ensure_ascii=False)

    latest_d = max((it['current_date'] for it in overview), default='-')
    info = {
        'symbol_count': len(overview),
        'latest_date': latest_d,
        'excel_path': ivserver.EXCEL_PATH,
    }
    with open(os.path.join(api_dir, 'info.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)

    # 前端静态资源（index.html + echarts 从 IV_Rank/static 复制，改写绝对路径）
    src_html = os.path.join(P_IVRANK, 'static', 'index.html')
    dst_html = os.path.join(out, 'index.html')
    if os.path.exists(src_html):
        with open(src_html, 'r', encoding='utf-8') as f:
            html = f.read()
        # 静态模式：绝对路径 echarts 改为相对路径
        html = html.replace('src="/echarts.min.js"', 'src="./echarts.min.js"')
        html = html.replace("'/echarts.min.js'", "'./echarts.min.js'")
        with open(dst_html, 'w', encoding='utf-8') as f:
            f.write(html)
    src_ech = os.path.join(P_IVRANK, 'static', 'echarts.min.js')
    if os.path.exists(src_ech) and not os.path.exists(os.path.join(out, 'echarts.min.js')):
        shutil.copy2(src_ech, os.path.join(out, 'echarts.min.js'))
    print(f"[iv_rank] 生成 {len(overview)} 个品种 api/*.json，latest {latest_d}")


# ================= 5. pcr PCR 跟踪 =================
def build_pcr(latest):
    """从 data/tables/*.csv 生成每品种全量 PCR 数据。"""
    out = os.path.join(SUB_DIR, 'pcr')
    data_dir = os.path.join(out, 'data')
    makedirs(data_dir)
    tables_dir = os.path.join(P_PCR, 'data', 'tables')
    if not os.path.isdir(tables_dir):
        print('[pcr] 跳过：tables 目录不存在')
        return

    def read_csv(name):
        path = os.path.join(tables_dir, name)
        out_d = {}
        with open(path, 'r', encoding='utf-8', newline='') as f:
            import csv
            r = csv.reader(f)
            header = next(r)
            keys = header[1:]
            for k in keys:
                out_d[k] = []
            dates = []
            for row in r:
                dates.append(row[0])
                for k, cell in zip(keys, row[1:]):
                    out_d[k].append(None if cell == '' else float(cell))
        return dates, out_d

    with open(os.path.join(tables_dir, 'varieties.json'), 'r', encoding='utf-8') as f:
        varieties = json.load(f)

    dates, price = read_csv('price.csv')
    _, call_oi = read_csv('call_oi.csv')
    _, put_oi = read_csv('put_oi.csv')

    with open(os.path.join(out, 'varieties.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'varieties': varieties,
            'date_range': {'first': dates[0] if dates else '', 'last': dates[-1] if dates else ''},
        }, f, ensure_ascii=False)

    ok = 0
    for v in varieties:
        key = v['key']
        if key not in price:
            continue
        p_arr, c_arr, put_arr = price[key], call_oi.get(key, []), put_oi.get(key, [])
        out_d, out_p, out_c, out_put, out_pcr, out_npcr = [], [], [], [], [], []
        for i, d in enumerate(dates):
            c = c_arr[i] if i < len(c_arr) and c_arr[i] is not None else 0.0
            p = put_arr[i] if i < len(put_arr) and put_arr[i] is not None else 0.0
            pr = p_arr[i] if i < len(p_arr) else None
            pcr = (p / c) if c and c > 0 else None
            denom = p + c
            npcr = ((p - c) / denom) if denom and denom > 0 else None
            out_d.append(d)
            out_p.append(pr)
            out_c.append(None if c == 0 else c)
            out_put.append(None if p == 0 else p)
            out_pcr.append(pcr)
            out_npcr.append(npcr)
        payload = {
            'key': key, 'dates': out_d, 'price': out_p,
            'call_oi': out_c, 'put_oi': out_put, 'pcr': out_pcr, 'norm_pcr': out_npcr,
        }
        # Windows 文件名不允许冒号：CZCE:AP -> CZCE_AP（前端 fetch 时同样替换）
        fname = key.replace(':', '_')
        with open(os.path.join(data_dir, f'{fname}.json'), 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        ok += 1
    print(f"[pcr] 生成 {ok} 个品种，数据区间 {dates[0]} ~ {dates[-1]}")


# ================= 6. gex GEX 分析 =================
def build_gex(latest):
    """为每个品种生成最新交易日 GEX 数据。"""
    out = os.path.join(SUB_DIR, 'gex')
    data_dir = os.path.join(out, 'data')
    makedirs(data_dir)
    if P_OIDIST not in sys.path:
        sys.path.insert(0, P_OIDIST)
    if P_GEX not in sys.path:
        sys.path.insert(0, P_GEX)
    try:
        from analyzer import analyze_variety
        from varieties import get_varieties_grouped
        import backend_gex
    except Exception as e:
        print('[gex] 跳过：import 失败', e)
        return

    groups = get_varieties_grouped()
    with open(os.path.join(out, 'varieties.json'), 'w', encoding='utf-8') as f:
        json.dump({'success': True, 'groups': groups}, f, ensure_ascii=False)

    ok, fail = 0, 0
    fails = []
    for g in groups:
        for v in g['varieties']:
            code = v['code']
            try:
                analysis = analyze_variety(code, latest)
                if not analysis.get('success'):
                    fail += 1
                    fails.append(code)
                    continue
                r = backend_gex.compute_commodity_gex(analysis)
                if r.get('success'):
                    with open(os.path.join(data_dir, f'{code}.json'), 'w', encoding='utf-8') as f:
                        json.dump(r, f, ensure_ascii=False)
                    ok += 1
                else:
                    fail += 1
                    fails.append(code)
            except Exception as e:
                fail += 1
                fails.append(f'{code}({type(e).__name__})')
    print(f"[gex] 生成 {ok} 个品种（失败 {fail}）{fails[:8]}")


# ================= 7. corr 相关性（纯静态复制） =================
def build_corr():
    """相关性页为纯静态（浏览器端 SheetJS 读 xlsx），整体复制到 static/corr/。"""
    src = P_CORR
    dst = os.path.join(STATIC_DIR, 'corr')
    if not os.path.isdir(src):
        print('[corr] 跳过：源目录不存在')
        return
    makedirs(dst)
    for name in os.listdir(src):
        # 排除本地服务端脚本与无关文件（静态站只保留浏览器资源）
        if name.startswith('.') or name in ('start.bat', 'server.py', '.workbuddy'):
            continue
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            if os.path.exists(d):
                shutil.rmtree(d)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    print('[corr] 复制到 static/corr/ 完成')


# ================= 8. site_info.json =================
def build_site_info(latest):
    info = {
        'build_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'latest_trade_date': latest,
        'sub_pages': {
            'overview': {'name': '期权市场总览', 'latest': latest},
            'oi_dist': {'name': '期权行情信息', 'latest': latest},
            'vol_hist': {'name': '历史波动率估计', 'latest': 'cache mtime'},
            'iv_rank': {'name': '隐含波动率分析', 'latest': 'api/info.json'},
            'pcr': {'name': '商品期权PCR跟踪', 'latest': 'tables'},
            'gex': {'name': '商品期权GEX分析', 'latest': latest},
            'corr': {'name': '商品行情与波动率相关性', 'latest': 'Corr.xlsx'},
        },
    }
    with open(os.path.join(STATIC_DIR, 'site_info.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print('[site_info] 生成 site_info.json')


def main():
    latest = detect_latest_date()
    print(f'=== 商品期权信息汇总面板 静态构建 ===')
    print(f'最新共同交易日: {latest}')
    makedirs(STATIC_DIR)
    makedirs(SUB_DIR)

    build_overview(latest)
    build_oi_dist(latest)
    build_vol_hist(latest)
    build_iv_rank(latest)
    build_pcr(latest)
    build_gex(latest)
    build_corr()
    build_site_info(latest)
    print('=== 构建完成 ===')


if __name__ == '__main__':
    main()
