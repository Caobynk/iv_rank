// build_data.js - Generate data.json from Corr.xlsx for the frontend.
// Mirrors compute.js detectSheets: price sheet = more FI.WI columns,
// iv sheet = more IV.WI columns. Output { price: <matrix>, iv: <matrix> }
// where each matrix is sheet_to_json(header:1) shape (the 'date' header row).
// Column headers in Corr.xlsx carry trailing spaces (e.g. "DCE_AIV.WI "),
// so we trim the header row before writing to keep compute.js basePrice/baseIv
// pairing correct. Run: node build_data.js  (re-run after editing Corr.xlsx)
const fs = require('fs');
const XLSX = require('./libs/xlsx.full.min.js');
const CA = require('./compute.js');

const buf = fs.readFileSync('Corr.xlsx');
const wb = XLSX.read(buf, { type: 'buffer' });

function matrixOf(name) {
  return XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, blankrows: false, defval: null });
}
function headerOf(mat) {
  for (const r of mat) {
    if (r && r.length && String(r[0]).trim().toLowerCase() === 'date') return r;
  }
  return null;
}
function normalizeHeader(mat) {
  for (const r of mat) {
    if (r && r.length && String(r[0]).trim().toLowerCase() === 'date') {
      for (let j = 0; j < r.length; j++) if (r[j] != null) r[j] = String(r[j]).trim();
      break;
    }
  }
  return mat;
}

let priceName = null, ivName = null;
for (const name of wb.SheetNames) {
  const hdr = headerOf(matrixOf(name));
  if (!hdr) continue;
  let nP = 0, nI = 0;
  for (let j = 1; j < hdr.length; j++) {
    const c = String(hdr[j] || '').trim();
    if (/FI\.WI$/i.test(c)) nP++;
    else if (/IV\.WI$/i.test(c)) nI++;
  }
  if (nP > nI && !priceName) priceName = name;
  else if (nI > nP && !ivName) ivName = name;
}
if (!priceName || !ivName) throw new Error('price/IV sheet not found in Corr.xlsx');

const price = normalizeHeader(matrixOf(priceName));
const iv = normalizeHeader(matrixOf(ivName));
fs.writeFileSync('data.json', JSON.stringify({ price, iv }));

// self-check: validate the data path the browser will use
const m = CA.parseWorkbookData(price, iv, { window: 20, ivMode: 'pct' });
const sig = (m.corrByDate[m.maxDate] || []).filter(x => x.absCorr >= 0.5);
console.log('data.json generated');
console.log('  price sheet :', priceName, '(', price.length, 'rows )');
console.log('  iv sheet    :', ivName, '(', iv.length, 'rows )');
console.log('  products    :', m.products.length);
console.log('  trade days  :', m.dates.length, '(', m.minDate, '~', m.maxDate, ')');
console.log('  latest day significant |r|>=0.5 :', sig.length, 'items');
