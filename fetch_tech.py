# -*- coding: utf-8 -*-
"""Fetch sina futures daily K for all varieties, compute tech indicators.
Output: fetch_tech_out.json (cwd)
Discipline: >=1s interval between requests, 3 retries, batch snapshot for quote.
"""
import urllib.request, json, time, sys, os

CODES = ["AU0","AG0","PT0","PD0","JM0","J0","RB0","I0","FG0","SA0","SC0","FU0","BU0","PG0","MA0","TA0","EG0","EB0","V0","SH0","UR0","L0","PP0","CU0","AL0","ZN0","PB0","LC0","SI0","PS0","RU0","NR0","BR0","P0","Y0","M0","A0","C0","LH0","CF0","SR0","SP0","LG0","EC0"]
NAMES = {"AU0":"黄金","AG0":"白银","PT0":"铂金","PD0":"钯金","JM0":"焦煤","J0":"焦炭","RB0":"螺纹","I0":"铁矿","FG0":"玻璃","SA0":"纯碱","SC0":"原油","FU0":"燃油","BU0":"沥青","PG0":"液化气","MA0":"甲醇","TA0":"PTA","EG0":"乙二醇","EB0":"苯乙烯","V0":"PVC","SH0":"烧碱","UR0":"尿素","L0":"塑料","PP0":"聚丙烯","CU0":"铜","AL0":"铝","ZN0":"锌","PB0":"铅","LC0":"碳酸锂","SI0":"工业硅","PS0":"多晶硅","RU0":"橡胶","NR0":"20号胶","BR0":"合成橡胶","P0":"棕榈油","Y0":"豆油","M0":"豆粕","A0":"豆一","C0":"玉米","LH0":"生猪","CF0":"棉花","SR0":"白糖","SP0":"纸浆","LG0":"原木","EC0":"集运欧线"}

def fetch(url, referer="https://finance.sina.com.cn", tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": referer,
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2)
    raise last

def get_daily(code):
    url = "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20t=/InnerFuturesNewService.getDailyKLine?symbol=" + code
    txt = fetch(url).decode("gbk", errors="replace")
    s = txt.index("[")
    e = txt.rindex("]") + 1
    arr = json.loads(txt[s:e])
    rows = [{"d": r["d"], "c": float(r["c"]), "h": float(r["h"]), "l": float(r["l"]),
             "o": float(r["o"]), "v": float(r["v"]), "p": float(r["p"])} for r in arr]
    return rows

def rsi14(closes):
    n = len(closes)
    if n < 16:
        return None
    gains, losses = [], []
    for i in range(1, n):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    # Wilder smoothing on the last 14
    ag = sum(gains[:14]) / 14.0
    al = sum(losses[:14]) / 14.0
    for i in range(14, len(gains)):
        ag = (ag * 13 + gains[i]) / 14.0
        al = (al * 13 + losses[i]) / 14.0
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)

def ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n

def compute(code, rows):
    closes = [r["c"] for r in rows]
    if len(rows) < 30:
        return {"code": code, "name": NAMES.get(code, code), "error": "insufficient rows"}
    last = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    prev5 = rows[-6] if len(rows) >= 6 else None
    day_chg = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else None
    week_chg = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else None
    win = rows[-20:]
    hi = max(win, key=lambda r: r["h"])
    lo = min(win, key=lambda r: r["l"])
    hi20, lo20 = hi["h"], lo["l"]
    pos = (closes[-1] - lo20) / (hi20 - lo20) * 100 if hi20 > lo20 else 50.0
    # open interest 5-day change (5 trading days ago = rows[-6])
    oi_now = last["p"]
    oi_5 = rows[-6]["p"] if len(rows) >= 6 else None
    oi_chg = (oi_now / oi_5 - 1) * 100 if oi_5 and oi_5 > 0 else None
    return {
        "code": code, "name": NAMES.get(code, code),
        "date": last["d"],
        "close": closes[-1],
        "day_chg": round(day_chg, 2) if day_chg is not None else None,
        "week_chg": round(week_chg, 2) if week_chg is not None else None,
        "ma5": round(ma(closes, 5), 2) if ma(closes, 5) else None,
        "ma10": round(ma(closes, 10), 2) if ma(closes, 10) else None,
        "ma20": round(ma(closes, 20), 2) if ma(closes, 20) else None,
        "rsi14": round(rsi14(closes), 1) if rsi14(closes) is not None else None,
        "hi20": hi20, "hi20_date": hi["d"],
        "lo20": lo20, "lo20_date": lo["d"],
        "pos20": round(pos, 1),
        "oi_now": int(oi_now), "oi_5": int(oi_5) if oi_5 else None,
        "oi_chg5": round(oi_chg, 1) if oi_chg is not None else None,
    }

def main():
    out = {}
    errs = []
    for i, code in enumerate(CODES):
        try:
            rows = get_daily(code)
            out[code] = compute(code, rows)
            print("[%02d/%02d] %s %s close=%.2f date=%s" % (i+1, len(CODES), code, out[code].get("name",""), out[code].get("close",0), out[code].get("date","")), flush=True)
        except Exception as e:
            errs.append(code)
            print("[%02d/%02d] %s ERROR %s" % (i+1, len(CODES), code, e), flush=True)
        if i < len(CODES) - 1:
            time.sleep(1.0)
    res = {"updated": time.strftime("%Y-%m-%d %H:%M:%S"), "varieties": out, "errors": errs}
    with open("fetch_tech_out.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("DONE. errors:", errs)

if __name__ == "__main__":
    main()
