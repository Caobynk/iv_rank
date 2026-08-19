#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""商品期权隐含波动率分位图 - 后端服务器"""

import http.server
import json
import urllib.parse
import os
import sys
import socket
import time
import threading
import webbrowser
import traceback
from datetime import datetime
import openpyxl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
# 端口文件：供「商品期权研究面板」Hub 发现本服务（与 Hub config.json 的 port_file 对应）
PORT_FILE = os.path.join(BASE_DIR, 'server_port.txt')

# Excel 数据文件路径（可移植）：
# 1) 优先读取环境变量 IV_EXCEL_PATH
# 2) 其次读取项目目录下的 data/Commodity_IV.xlsx（迁移时把数据文件放这里最方便）
# 3) 最后回退到原绝对路径（兼容当前设备）
def resolve_excel_path():
    env_path = os.environ.get('IV_EXCEL_PATH', '').strip()
    if env_path and os.path.isfile(env_path):
        return env_path
    local_path = os.path.join(BASE_DIR, 'data', 'Commodity_IV.xlsx')
    if os.path.isfile(local_path):
        return local_path
    if env_path:
        return env_path  # 即使不存在也返回，便于报错时显示用户意图
    return r'C:\temp\Data\Commodity_IV.xlsx'

EXCEL_PATH = resolve_excel_path()

# 全局数据缓存
_data_cache = None
_data_lock = threading.Lock()

# 心跳检测：网页关闭后自动释放端口
_last_heartbeat = time.time()
_heartbeat_lock = threading.Lock()
HEARTBEAT_TIMEOUT = 15  # 超过此秒数无心跳则自动关闭
_server_instance = None

# 交易所前缀映射
EXCHANGE_MAP = {
    'DCE': '大商所',
    'CZC': '郑商所',
    'SHF': '上期所',
    'GFE': '广期所',
    'INE': '能源中心',
}

# 品种代码 → 中文简称映射表（统一美观的简称）
SYMBOL_SHORT_NAME_MAP = {
    # 大商所 DCE
    'A': '豆一', 'B': '豆二', 'C': '玉米', 'CS': '玉米淀粉',
    'EB': '苯乙烯', 'EG': '乙二醇', 'I': '铁矿石', 'JD': '鸡蛋',
    'JM': '焦煤', 'L': '塑料', 'LG': '原木', 'LH': '生猪',
    'M': '豆粕', 'P': '棕榈油', 'PG': 'LPG', 'PP': '聚丙烯',
    'V': 'PVC', 'Y': '豆油', 'BZ': '纯苯',
    # 郑商所 CZC
    'AP': '苹果', 'CF': '棉花', 'CJ': '红枣', 'FG': '玻璃',
    'MA': '甲醇', 'OI': '菜油', 'PF': '短纤', 'PK': '花生',
    'PL': '丙烯', 'PR': '瓶片', 'PX': '对二甲苯', 'RM': '菜粕',
    'SA': '纯碱', 'SF': '硅铁', 'SM': '锰硅', 'SR': '白糖',
    'SH': '烧碱', 'TA': 'PTA', 'UR': '尿素', 'ZC': '动力煤',
    # 上期所 SHF
    'AD': '铸铝合金', 'AG': '白银', 'AL': '铝', 'AO': '氧化铝',
    'BR': '丁二烯橡胶', 'BU': '沥青', 'CU': '铜', 'FU': '燃料油',
    'NI': '镍', 'OP': '双胶纸', 'PB': '铅', 'RB': '螺纹钢',
    'RU': '天胶', 'SN': '锡', 'SP': '纸浆', 'ZN': '锌', 'AU': '黄金',
    # 广期所 GFE（2025-11 上市铂 PT / 钯 PD）
    'LC': '碳酸锂', 'PS': '多晶硅', 'PT': '铂', 'PD': '钯', 'SI': '工业硅',
    # 能源中心 INE
    'BC': '国际铜', 'NR': '20号胶', 'SC': '原油',
}


def load_excel_data():
    """读取Excel文件，返回品种数据字典"""
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb['IV数据']
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # Row 0: NaN, 收盘价, ...（标题行）
    # Row 1: NaN, close, ...（英文标题）
    # Row 2: 日期, 中文名...（中文名行）
    # Row 3: Date, 代码...（代码行）
    # Row 4+: 数据行

    if len(rows) < 5:
        return {}

    chinese_names = rows[2]
    codes = rows[3]

    symbols = {}
    for col_idx in range(1, len(codes)):
        code_raw = codes[col_idx]
        name_raw = chinese_names[col_idx] if col_idx < len(chinese_names) else None

        if not code_raw or 'IV.WI' not in str(code_raw):
            continue

        code = str(code_raw).strip()

        # 品种代码（交易所前缀_后面的部分，去掉IV.WI后缀）
        symbol_code = code.split('_')[1].replace('IV.WI', '').strip() if '_' in code else ''

        # 提取交易所
        prefix = code.split('_')[0] if '_' in code else ''
        exchange = EXCHANGE_MAP.get(prefix, prefix)

        # 简称：优先使用统一映射表，确保美观一致
        short_name = SYMBOL_SHORT_NAME_MAP.get(symbol_code, '')

        # 完整中文名
        if name_raw and str(name_raw).strip():
            name = str(name_raw).strip()
        elif short_name:
            name = short_name + '主力平值IV'
        else:
            name = code
            short_name = symbol_code

        dates = []
        values = []
        for row in rows[4:]:
            if row is None or len(row) <= col_idx:
                continue
            date_val = row[0]
            iv_val = row[col_idx]
            if date_val is not None and iv_val is not None:
                try:
                    iv_float = float(iv_val)
                    dates.append(date_val)
                    values.append(iv_float)
                except (ValueError, TypeError):
                    pass

        if len(values) > 0:
            symbols[code] = {
                'name': name,
                'short_name': short_name,
                'code': code,
                'exchange': exchange,
                'dates': dates,
                'values': values,
            }

    return symbols


def get_data():
    """获取缓存数据，如未加载则加载"""
    global _data_cache
    if _data_cache is None:
        with _data_lock:
            if _data_cache is None:
                _data_cache = load_excel_data()
    return _data_cache


def refresh_data():
    """强制重新加载Excel数据"""
    global _data_cache
    with _data_lock:
        _data_cache = load_excel_data()
    return _data_cache


def date_to_str(d):
    """将日期对象转为字符串（datetime/date 均支持 strftime）"""
    if hasattr(d, 'strftime'):
        return d.strftime('%Y-%m-%d')
    return str(d)


def calc_percentile(values, current):
    """计算current值在values中的百分位数（0-100）"""
    if not values:
        return 0
    count = sum(1 for v in values if v <= current)
    return count / len(values) * 100


def get_overview(days=500):
    """获取所有品种的概览数据"""
    data = get_data()
    result = []
    for code, info in data.items():
        values = info['values']
        dates = info['dates']
        if not values:
            continue

        # 取最近N个交易日
        recent_values = values[-days:]
        recent_dates = dates[-days:]

        current = recent_values[-1]
        current_date = date_to_str(recent_dates[-1])

        min_val = min(recent_values)
        max_val = max(recent_values)
        avg_val = sum(recent_values) / len(recent_values)
        percentile = calc_percentile(recent_values, current)

        # 计算当前位置在范围中的比例
        range_val = max_val - min_val
        position = (current - min_val) / range_val * 100 if range_val > 0 else 50

        result.append({
            'code': code,
            'name': info['name'],
            'short_name': info['short_name'],
            'exchange': info['exchange'],
            'current': round(current * 100, 2),
            'min': round(min_val * 100, 2),
            'max': round(max_val * 100, 2),
            'avg': round(avg_val * 100, 2),
            'percentile': round(percentile, 1),
            'position': round(position, 1),
            'current_date': current_date,
            'data_count': len(recent_values),
        })

    # 按当前波动率降序排列
    result.sort(key=lambda x: x['current'], reverse=True)
    return result


def get_detail(code, days=500):
    """获取单个品种的详细走势数据"""
    data = get_data()
    if code not in data:
        return None

    info = data[code]
    recent_values = info['values'][-days:]
    recent_dates = info['dates'][-days:]

    # 计算分位数序列（滚动）
    return {
        'code': code,
        'name': info['name'],
        'short_name': info['short_name'],
        'exchange': info['exchange'],
        'dates': [date_to_str(d) for d in recent_dates],
        'values': [round(v * 100, 2) for v in recent_values],
        'current': round(recent_values[-1] * 100, 2),
        'current_date': date_to_str(recent_dates[-1]),
        'min': round(min(recent_values) * 100, 2),
        'max': round(max(recent_values) * 100, 2),
        'avg': round(sum(recent_values) / len(recent_values) * 100, 2),
        'percentile': round(calc_percentile(recent_values, recent_values[-1]), 1),
        'data_count': len(recent_values),
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == '/' or path == '/index.html':
                self.serve_file('index.html', 'text/html; charset=utf-8')
            elif path == '/echarts.min.js':
                self.serve_file('echarts.min.js', 'application/javascript; charset=utf-8')
            elif path == '/api/overview':
                days = int(params.get('days', ['500'])[0])
                data = get_overview(days)
                self.json_response({'data': data, 'count': len(data)})
            elif path == '/api/detail':
                code = params.get('code', [''])[0]
                days = int(params.get('days', ['500'])[0])
                data = get_detail(code, days)
                if data:
                    self.json_response(data)
                else:
                    self.json_response({'error': 'Symbol not found'}, 404)
            elif path == '/api/refresh':
                refresh_data()
                days = int(params.get('days', ['500'])[0])
                data = get_overview(days)
                self.json_response({'data': data, 'count': len(data), 'refreshed': True})
            elif path == '/api/info':
                data = get_data()
                info = {
                    'excel_path': EXCEL_PATH,
                    'symbol_count': len(data),
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
                # 获取数据日期范围
                if data:
                    all_dates = []
                    for v in data.values():
                        if v['dates']:
                            all_dates.append(v['dates'][-1])
                    if all_dates:
                        latest = max(all_dates)
                        info['latest_date'] = date_to_str(latest)
                self.json_response(info)
            elif path == '/api/heartbeat':
                global _last_heartbeat
                with _heartbeat_lock:
                    _last_heartbeat = time.time()
                self.json_response({'ok': True})
            elif path == '/api/shutdown':
                self.json_response({'ok': True})
                threading.Thread(target=shutdown_server, daemon=True).start()
            else:
                self.send_error(404)
        except Exception as e:
            traceback.print_exc()
            self.json_response({'error': str(e)}, 500)

    def serve_file(self, filename, content_type):
        filepath = os.path.join(STATIC_DIR, filename)
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def log_message(self, format, *args):
        pass  # 静默日志


def find_free_port():
    """自动查找可用端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def heartbeat_monitor():
    """后台监控心跳，网页关闭后自动停止服务器释放端口"""
    global _last_heartbeat
    # 启动后给予30秒宽限期（等待浏览器打开）
    with _heartbeat_lock:
        _last_heartbeat = time.time() + 15  # 宽限期

    while True:
        time.sleep(5)
        with _heartbeat_lock:
            elapsed = time.time() - _last_heartbeat
        if elapsed > HEARTBEAT_TIMEOUT:
            print(f'\n网页已关闭（无心跳 {HEARTBEAT_TIMEOUT}秒），自动释放端口...')
            shutdown_server()


def _remove_port_file():
    """清理端口文件（尽力而为），避免 Hub 读到陈旧端口"""
    try:
        if os.path.exists(PORT_FILE):
            os.remove(PORT_FILE)
    except OSError:
        pass


def shutdown_server():
    """优雅关闭服务器"""
    global _server_instance
    _remove_port_file()
    if _server_instance:
        threading.Thread(target=lambda: (_server_instance.shutdown(), os._exit(0)), daemon=True).start()
    else:
        os._exit(0)


def main():
    global _server_instance, _last_heartbeat

    port = find_free_port()

    # 写入端口文件，供汇总面板 Hub 发现本服务（Hub 读 <dir>/server_port.txt）
    try:
        with open(PORT_FILE, 'w', encoding='utf-8') as f:
            f.write(str(port))
    except OSError:
        pass

    print(f'=' * 50)
    print(f'  商品期权隐含波动率分位图')
    print(f'=' * 50)
    print(f'Excel路径: {EXCEL_PATH}')
    print(f'服务端口: {port}（自动分配）')
    print(f'正在加载数据...')

    # 预加载数据
    try:
        data = get_data()
    except FileNotFoundError:
        print('[错误] 未找到 Excel 数据文件！')
        print(f'       查找路径: {EXCEL_PATH}')
        print('       请确认项目 data/ 目录下存在 Commodity_IV.xlsx，')
        print('       或通过环境变量 IV_EXCEL_PATH 指定数据文件路径。')
        sys.exit(1)
    except KeyError as e:
        print('[错误] Excel 数据文件结构不匹配！')
        print(f'       缺少工作表或列: {e}')
        print('       请确认数据文件为「IV数据」工作表格式（含 日期/收盘价/各品种IV列）。')
        sys.exit(1)
    print(f'已加载 {len(data)} 个品种')

    if data:
        all_dates = []
        for v in data.values():
            if v['dates']:
                all_dates.extend([v['dates'][0], v['dates'][-1]])
        if all_dates:
            print(f'数据日期范围: {date_to_str(min(all_dates))} ~ {date_to_str(max(all_dates))}')

    print(f'-' * 50)
    url = f'http://localhost:{port}'
    print(f'访问地址: {url}')
    print(f'关闭网页后将自动释放端口（{HEARTBEAT_TIMEOUT}秒无心跳）')
    print(f'按 Ctrl+C 也可手动停止')
    print(f'=' * 50)

    # 启动心跳监控线程
    monitor_thread = threading.Thread(target=heartbeat_monitor, daemon=True)
    monitor_thread.start()

    # 启动HTTP服务器
    _server_instance = http.server.HTTPServer(('127.0.0.1', port), Handler)

    # 延迟1秒后自动打开浏览器（被汇总面板 Hub 以 NO_BROWSER=1 启动时跳过，避免重复开页）
    def open_browser():
        if os.environ.get('NO_BROWSER') == '1':
            return
        time.sleep(1)
        # 本地模式标记：前端据此走 Python 动态后端（days 可调 / refresh / 心跳 / 关停）
        webbrowser.open(url + '/?local=1')
    threading.Thread(target=open_browser, daemon=True).start()

    try:
        _server_instance.serve_forever()
    except KeyboardInterrupt:
        print('\n手动停止服务...')
    finally:
        # 清理端口文件（Ctrl+C 退出路径）
        _remove_port_file()
        if _server_instance:
            _server_instance.server_close()
        print('端口已释放，服务已停止。')


if __name__ == '__main__':
    main()
