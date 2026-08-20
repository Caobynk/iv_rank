# -*- coding: utf-8 -*-
"""generate_frontends.py - 从各子服务模板生成静态版前端（一次性工具，结果已提交仓库）

静态版改造点：
  1. echarts 引用 → 本地相对路径 ./echarts.min.js
  2. 模板变量 {{ default_date }} → 固定最新交易日
  3. fetch /api/* → 静态相对路径（data.json / varieties.json / data/{code}.json）
  4. 删除心跳/关闭/刷新等后端专属逻辑
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, 'static', 'sub')
LATEST = '2026-08-18'

# ---------- 工具 ----------
def read(p):
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()

def write(p, s):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)

def strip_block(html, start_marker, end_marker=None, keep_end=False):
    """删除从 start_marker 到 end_marker（含）的整块；end_marker 为 None 时删到文件尾前。"""
    i = html.find(start_marker)
    if i < 0:
        return html
    if end_marker is None:
        return html[:i]
    j = html.find(end_marker, i)
    if j < 0:
        return html
    j += len(end_marker)
    return html[:i] + html[j:]

# ---------- oi_dist 最痛点 ----------
def gen_oi_dist():
    src = read(r'D:\WorkBuddy\商品期权成交持仓分布及最痛点位绘制\templates\index.html')
    h = src
    h = h.replace('src="/static/echarts.min.js"', 'src="./echarts.min.js"')
    h = h.replace('"{{ default_date }}"', f'"{LATEST}"')
    # fetch /api/varieties -> varieties.json
    h = h.replace("const res = await fetch('/api/varieties');", "const res = await fetch('varieties.json');")
    # fetch /api/data?variety&date -> data/{variety}.json（静态版固定最新交易日，date 参数忽略）
    old_query = "const res = await fetch(`/api/data?variety=${encodeURIComponent(variety)}&date=${encodeURIComponent(date)}`);"
    new_query = "const res = await fetch(`data/${encodeURIComponent(variety)}.json`);"
    assert old_query in h, 'oi_dist fetch/data 行未匹配'
    h = h.replace(old_query, new_query)
    # 删除心跳保活
    h = re.sub(r"\s*// 心跳保活\n\s*setInterval\(\(\) => \{ fetch\('/api/heartbeat', \{method:'POST'\}\)\.catch\(\(\)=>\{\}\); \}, 5000\);", '', h)
    # 删除关闭网页停止服务
    h = re.sub(r"\s*// 关闭网页时停止服务\n\s*window\.addEventListener\('beforeunload', \(\) => \{\n\s*navigator\.sendBeacon\('/api/shutdown'\);\n\s*\}\);", '', h)
    # 删除停止服务按钮相关（保留按钮但改为提示，简化：删除 stopServer 函数）
    h = h.replace("  document.getElementById('btn-stop').onclick = stopServer;\n", "")
    h = re.sub(r"\nasync function stopServer\(\) \{.*?\n\}\n", "\n", h, flags=re.S)
    # 日期输入框静态版禁用（快照固定最新交易日）
    h = h.replace('<input type="date" id="date">', f'<input type="date" id="date" value="{LATEST}" disabled>')
    # 查询按钮文案微调
    h = h.replace('数据抓取中，请稍候…（大商所需启动浏览器，可能稍慢）', '加载静态数据…')
    write(os.path.join(STATIC, 'oi_dist', 'index.html'), h)
    print('oi_dist OK')

# ---------- vol_hist 波动率 ----------
def gen_vol_hist():
    src = read(r'D:\WorkBuddy\商品期货历史波动率估计\templates\index.html')
    h = src
    h = h.replace('src="/static/echarts.min.js"', 'src="./echarts.min.js"')
    # fetch /api/varieties -> varieties.json
    h = h.replace("return fetch('/api/varieties').then(r => r.json()).then(groups => {",
                  "return fetch('varieties.json').then(r => r.json()).then(groups => {")
    # fetch /api/data?symbol&window&startYear -> data/{symbol}.json（静态版固定 window=30 startYear=auto）
    old_query = "const resp = await fetch(`/api/data?symbol=${encodeURIComponent(symbol)}&window=${window}&startYear=${encodeURIComponent(startYear)}${refresh ? '&refresh=1' : ''}`);"
    new_query = "const resp = await fetch(`data/${encodeURIComponent(symbol)}.json`);"
    assert old_query in h, 'vol_hist fetch/data 行未匹配'
    h = h.replace(old_query, new_query)
    # window / startYear 下拉禁用（静态快照 window=30, startYear=auto），并提示
    h = h.replace('<select id="window">', '<select id="window" disabled>')
    h = h.replace('<select id="startYear"></select>', '<select id="startYear" disabled></select>')
    # 删除 heartbeat / shutdown
    h = re.sub(r"\s*function notifyShutdown\(\) \{.*?\n\}\n", "\n", h, flags=re.S)
    h = h.replace("window.addEventListener('beforeunload', notifyShutdown);\nwindow.addEventListener('pagehide', notifyShutdown);\n", "")
    h = h.replace("setInterval(() => { try { navigator.sendBeacon('/heartbeat'); } catch (e) {} }, 30000);\n", "")
    # 刷新按钮禁用
    h = h.replace('<button id="refresh" class="primary">刷新数据</button>', '<button id="refresh" class="primary" disabled>刷新数据（静态版）</button>')
    write(os.path.join(STATIC, 'vol_hist', 'index.html'), h)
    print('vol_hist OK')

# ---------- pcr PCR 跟踪 ----------
def gen_pcr():
    src = read(r'D:\WorkBuddy\商品期权PCR跟踪\web\templates\index.html')
    h = src
    h = h.replace('src="/static/echarts.min.js"', 'src="./echarts.min.js"')
    # fetch /api/varieties -> varieties.json
    h = h.replace("const r = await fetch('/api/varieties');", "const r = await fetch('varieties.json');")
    # fetch /api/data?key&start&end -> data/{key}.json（全量数据，前端本地按 start/end 过滤）
    # 注意：Windows 文件名不允许冒号，静态文件名 key.replace(':', '_')，fetch 时同样替换
    old_query = "const r = await fetch(`/api/data?key=${encodeURIComponent(key)}&start=${start}&end=${end}`);"
    new_query = "const fname = key.replace(':', '_');\n    const r = await fetch(`data/${encodeURIComponent(fname)}.json`);"
    assert old_query in h, 'pcr fetch/data 行未匹配'
    h = h.replace(old_query, new_query)
    # 返回全量后，前端做日期过滤：在 draw() 的 fetch 之后插入过滤逻辑
    filter_js = """
    // 静态版：data.json 为全量，按 start/end 本地过滤
    if (d.dates && d.dates.length) {
      const idxs = [];
      d.dates.forEach((dt, i) => {
        if ((!start || dt >= start) && (!end || dt <= end)) idxs.push(i);
      });
      const pick = arr => idxs.map(i => (arr && i < arr.length) ? arr[i] : null);
      d.dates = idxs.map(i => d.dates[i]);
      d.price = pick(d.price);
      d.call_oi = pick(d.call_oi);
      d.put_oi = pick(d.put_oi);
      d.pcr = pick(d.pcr);
      d.norm_pcr = pick(d.norm_pcr);
    }
"""
    anchor = "    if(!d.dates || d.dates.length===0){ setStatus('该区间无数据。'); chart.clear(); return; }"
    assert anchor in h, 'pcr 过滤锚点未匹配'
    h = h.replace(anchor, filter_js + "\n" + anchor)
    # 删除更新数据 / 停止服务按钮与逻辑
    h = h.replace('<button id="update">更新数据</button>\n    <button class="danger" id="stop">停止服务</button>', '<span style="font-size:12px;color:#888">静态版 · 数据由构建脚本更新</span>')
    # 删除 update 相关 JS（pollUpdate 等）
    h = re.sub(r"\ndocument\.getElementById\('update'\)\.onclick = async function\(\)\{.*?\n\};\n", "\n", h, flags=re.S)
    h = re.sub(r"\nfunction pollUpdate\(\)\{.*?\n\}\n", "\n", h, flags=re.S)
    h = re.sub(r"\ndocument\.getElementById\('stop'\)\.onclick = \(\)=>\{.*?\n\};\n", "\n", h, flags=re.S)
    # 删除 pagehide/beforeunload shutdown
    h = h.replace("window.addEventListener('pagehide', ()=> navigator.sendBeacon('/api/shutdown'));\n", "")
    h = h.replace("window.addEventListener('beforeunload', ()=> navigator.sendBeacon('/api/shutdown'));\n", "")
    write(os.path.join(STATIC, 'pcr', 'index.html'), h)
    print('pcr OK')

# ---------- gex GEX ----------
def gen_gex():
    src = read(r'D:\WorkBuddy\GEX观察\gex_commodity.html')
    h = src
    h = h.replace('src="/echarts.min.js"', 'src="./echarts.min.js"')
    # fetch /api/commodity/varieties -> varieties.json
    h = h.replace("const r = await fetch('/api/commodity/varieties', { cache: 'no-store' });",
                  "const r = await fetch('varieties.json', { cache: 'no-store' });")
    # fetch /api/commodity/gex -> data/{variety}.json（静态版固定最新交易日）
    old_query = "const resp = await fetch('/api/commodity/gex?' + params.toString(), { cache: 'no-store' });"
    new_query = "const resp = await fetch(`data/${encodeURIComponent(variety)}.json`, { cache: 'no-store' });"
    assert old_query in h, 'gex fetch 行未匹配'
    h = h.replace(old_query, new_query)
    # 静态版：交易日固定为最新缓存日，隐藏日期选择
    h = h.replace("document.getElementById('tradeDate').value = defaultYesterday();",
                  "document.getElementById('tradeDate').value = '2026-08-18';")
    h = h.replace('<div class="field">交易日<input type="date" id="tradeDate"></div>',
                  '<div class="field">交易日<input type="date" id="tradeDate" value="2026-08-18" disabled></div>')
    # 删除心跳/关闭
    h = re.sub(r"\nfunction heartbeat\(\) \{.*?\n\}\n", "\n", h, flags=re.S)
    h = re.sub(r"\nwindow\.addEventListener\('beforeunload', \(\) => \{\n\s*try \{ navigator\.sendBeacon\('/api/shutdown'\); \} catch \(e\) \{\}\n\}\);\n", "\n", h, flags=re.S)
    h = h.replace("setInterval(heartbeat, 30000);\n", "")
    write(os.path.join(STATIC, 'gex', 'index.html'), h)
    print('gex OK')

if __name__ == '__main__':
    gen_oi_dist()
    gen_vol_hist()
    gen_pcr()
    gen_gex()
    print('全部完成')
