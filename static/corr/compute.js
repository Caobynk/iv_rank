/*
 * compute.js — 商品行情 × 隐含波动率 相关性计算核心
 * 同时可在浏览器(window.CorrAnalyzer)与 Node(module.exports) 中运行。
 *
 * 计算思路：
 *   1. 从「价格指数」与「IV数据」两个 sheet 中定位表头行（首列为 Date 的那一行）。
 *   2. 价格列形如 AFI.WI / AGFI.WI，IV 列形如 DCE_AIV.WI / SHF_AGIV.WI，
 *      通过提取基础合约代码（如 A / AG / AL）将两者配对。
 *   3. 按交易日对齐价格与 IV，计算每日涨跌幅：
 *        价格涨跌幅  = P_t / P_{t-1} - 1
 *        IV 涨跌幅    = IV_t / IV_{t-1} - 1   （ivMode='pct'，默认）
 *        IV 绝对变化  = IV_t - IV_{t-1}        （ivMode='abs'，可选）
 *   4. 以「最近 window=20 个交易日」为滑动窗口，计算每个品种价格变化与 IV 变化
 *      的 Pearson 相关系数。
 *   5. 预计算所有交易日的相关性，供网页按日期即时展示。
 */
(function (global) {
  'use strict';

  // ---- 命名常量（替代魔法数字）----
  const EXCEL_EPOCH_DAYS = 25569; // 1899-12-30 与 1970-01-01 相差天数（Excel 日期序列号基准）
  const DEFAULT_WINDOW = 20;     // 默认滚动窗口（交易日）

  // ---- 日期格式化：统一为 'YYYY-MM-DD' ----
  function pad2(n) { return String(n).padStart(2, '0'); }

  function fmtDate(v) {
    if (v == null) return null;
    if (v instanceof Date) {
      return v.getFullYear() + '-' + pad2(v.getMonth() + 1) + '-' + pad2(v.getDate());
    }
    if (typeof v === 'number') {
      // Excel 序列号：1899-12-30 与 1970-01-01 相差天数（UTC 计算避免时区漂移）
      const d = new Date(Math.round((v - EXCEL_EPOCH_DAYS) * 86400) * 1000);
      return d.getUTCFullYear() + '-' + pad2(d.getUTCMonth() + 1) + '-' + pad2(d.getUTCDate());
    }
    if (typeof v === 'string') {
      const s = v.trim();
      const t = Date.parse(s);
      if (!isNaN(t)) {
        const d = new Date(t);
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
      }
      return s;
    }
    return String(v);
  }

  function toNum(v) {
    if (v == null) return null;
    if (typeof v === 'number') return isFinite(v) ? v : null;
    if (typeof v === 'string') {
      const s = v.replace(/,/g, '').trim();
      if (s === '') return null;
      const n = parseFloat(s);
      return isFinite(n) ? n : null;
    }
    return null;
  }

  // 价格列：AFI.WI -> A ；AGFI.WI -> AG
  function basePrice(c) {
    c = String(c);
    const m = c.match(/^(.*?)FI\.WI$/);
    return m ? m[1] : c;
  }
  // IV 列：DCE_AIV.WI -> A ；SHF_AGIV.WI -> AG
  function baseIv(c) {
    c = String(c);
    c = c.replace(/^[A-Z]+_/, '');
    const m = c.match(/^(.*?)IV\.WI$/);
    return m ? m[1] : c;
  }

  function pearson(x, y) {
    const n = x.length;
    if (n < 2) return null;
    let mx = 0, my = 0;
    for (let i = 0; i < n; i++) { mx += x[i]; my += y[i]; }
    mx /= n; my /= n;
    let cov = 0, sx = 0, sy = 0;
    for (let i = 0; i < n; i++) {
      const dx = x[i] - mx, dy = y[i] - my;
      cov += dx * dy; sx += dx * dx; sy += dy * dy;
    }
    if (sx <= 0 || sy <= 0) return null;
    return cov / Math.sqrt(sx * sy);
  }

  // 涨跌幅序列（第 0 项为 null）
  function pctChanges(arr) {
    const n = arr.length;
    const out = new Array(n).fill(null);
    for (let i = 1; i < n; i++) {
      const prev = arr[i - 1], cur = arr[i];
      if (prev != null && cur != null && prev !== 0) out[i] = cur / prev - 1;
      else out[i] = null;
    }
    return out;
  }

  // 在矩阵中定位表头行（首列等于 'date' 的那一行）
  function findHeader(m) {
    for (let i = 0; i < m.length; i++) {
      const r = m[i];
      if (r && r.length && String(r[0]).trim().toLowerCase() === 'date') {
        return { header: r, idx: i };
      }
    }
    return null;
  }

  /**
   * 解析两个 sheet 的矩阵数据，返回计算模型。
   * @param {Array<Array>} priceMatrix 价格指数 sheet（array of arrays）
   * @param {Array<Array>} ivMatrix    IV数据 sheet（array of arrays）
   * @param {Object} opts { window=20, ivMode='pct'|'abs' }
   */
  function parseWorkbookData(priceMatrix, ivMatrix, opts) {
    opts = opts || {};
    const W = opts.window || DEFAULT_WINDOW;
    const ivMode = opts.ivMode || 'pct';

    const ph = findHeader(priceMatrix);
    const ih = findHeader(ivMatrix);
    if (!ph || !ih) throw new Error('未在两个 sheet 中找到首列为 Date 的表头行');

    const priceHeader = ph.header;
    const priceRows = priceMatrix.slice(ph.idx + 1);
    const ivHeader = ih.header;
    const ivRows = ivMatrix.slice(ih.idx + 1);

    // 建立列映射（按基础合约代码去重，保留首次出现）
    const pcols = {}, icols = {};
    for (let j = 1; j < priceHeader.length; j++) {
      const c = priceHeader[j];
      if (c == null) continue;
      const b = basePrice(c);
      if (!(b in pcols)) pcols[b] = { code: String(c), idx: j };
    }
    for (let j = 1; j < ivHeader.length; j++) {
      const c = ivHeader[j];
      if (c == null) continue;
      const b = baseIv(c);
      if (!(b in icols)) icols[b] = { code: String(c), idx: j };
    }

    // IV 查找表：base -> { dateStr: value }
    const ivMap = {};
    for (const b in icols) {
      const m = {};
      const idx = icols[b].idx;
      for (const row of ivRows) {
        const ds = fmtDate(row[0]);
        if (!ds) continue;
        const v = toNum(row[idx]);
        if (v != null) m[ds] = v;
      }
      ivMap[b] = m;
    }

    // 按交易日对齐价格与 IV，构建品种序列
    const products = [];
    for (const b in pcols) {
      if (!(b in icols)) continue; // 仅保留价格、IV 都存在的品种
      const pIdx = pcols[b].idx;
      const D = [], P = [], V = [];
      for (const row of priceRows) {
        const ds = fmtDate(row[0]);
        if (!ds) continue;
        const p = toNum(row[pIdx]);
        const ivm = ivMap[b];
        if (p == null || !ivm || !(ds in ivm)) continue;
        D.push(ds); P.push(p); V.push(ivm[ds]);
      }
      if (D.length < W + 1) continue; // 数据不足以计算一个窗口
      products.push({ base: b, priceCode: pcols[b].code, ivCode: icols[b].code, D, P, V });
    }

    // 计算涨跌幅序列
    for (const pr of products) {
      pr.rp = pctChanges(pr.P);
      if (ivMode === 'abs') {
        const n = pr.V.length;
        const rv = new Array(n).fill(null);
        for (let i = 1; i < n; i++) {
          if (pr.V[i - 1] != null && pr.V[i] != null) rv[i] = pr.V[i] - pr.V[i - 1];
          else rv[i] = null;
        }
        pr.rv = rv;
      } else {
        pr.rv = pctChanges(pr.V);
      }
    }

    // 预计算所有交易日、所有品种的相关性
    const corrByDate = {};
    for (const pr of products) {
      const n = pr.D.length;
      for (let t = W; t < n; t++) {
        const x = [], y = [];
        for (let k = t - W + 1; k <= t; k++) {
          const a = pr.rp[k], b = pr.rv[k];
          if (a != null && b != null) { x.push(a); y.push(b); }
        }
        if (x.length < W - 2) continue; // 窗口内有效样本不足
        const c = pearson(x, y);
        if (c == null) continue;
        const ds = pr.D[t];
        if (!corrByDate[ds]) corrByDate[ds] = [];
        corrByDate[ds].push({
          base: pr.base,
          priceCode: pr.priceCode,
          ivCode: pr.ivCode,
          corr: c,
          absCorr: Math.abs(c),
          iv: pr.V[t],
          dateIndex: t,
          product: pr
        });
      }
    }

    const dates = Object.keys(corrByDate).sort();
    return {
      products,
      corrByDate,
      dates,
      window: W,
      ivMode,
      minDate: dates[0],
      maxDate: dates[dates.length - 1]
    };
  }

  // ---- 浏览器侧：直接解析 Excel 文件（含工作表自动识别）----
  function detectSheets(wb) {
    let priceName = null, ivName = null;
    for (const name of wb.SheetNames) {
      const ws = wb.Sheets[name];
      if (!ws) continue;
      const mat = XLSX.utils.sheet_to_json(ws, { header: 1, blankrows: false, defval: null });
      let hdr = null;
      for (const r of mat) {
        if (r && r.length && String(r[0]).trim().toLowerCase() === 'date') { hdr = r; break; }
      }
      if (!hdr) continue;
      let nP = 0, nI = 0;
      for (let j = 1; j < hdr.length; j++) {
        const c = String(hdr[j] || '');
        if (/FI\.WI$/i.test(c)) nP++;
        else if (/IV\.WI$/i.test(c)) nI++;
      }
      if (nP > nI && !priceName) priceName = name;
      else if (nI > nP && !ivName) ivName = name;
    }
    return { priceName, ivName };
  }

  // 读取 ArrayBuffer，自动识别价格/IV 工作表，返回与 parseWorkbookData 相同的模型
  function parseFile(buf, opts) {
    const wb = XLSX.read(buf, { type: 'array' });
    const det = detectSheets(wb);
    if (!det.priceName || !det.ivName) {
      throw new Error('未找到包含价格(FI.WI)与IV(IV.WI)列的两个工作表');
    }
    const priceMat = XLSX.utils.sheet_to_json(wb.Sheets[det.priceName], { header: 1, blankrows: false, defval: null });
    const ivMat = XLSX.utils.sheet_to_json(wb.Sheets[det.ivName], { header: 1, blankrows: false, defval: null });
    return parseWorkbookData(priceMat, ivMat, opts);
  }

  const API = { parseWorkbookData, parseFile, detectSheets, pearson, pctChanges, fmtDate, basePrice, baseIv };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else global.CorrAnalyzer = API;
})(typeof window !== 'undefined' ? window : globalThis);
