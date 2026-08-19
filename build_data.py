"""Build static JSON for Cloudflare Pages deployment (Plan A1).

Reuses server.py's pure data functions so the online static site and the
local Python backend share one source of truth. Output format matches the
/api/* responses exactly, so the frontend needs no parsing changes.

Generated files (committed to git, served statically by Pages):
  static/api/overview.json        -> {'data': [...], 'count': N}
  static/api/detail_<CODE>.json   -> detail dict for one symbol
  static/api/info.json            -> {symbol_count, latest_date, excel_path}

Usage:
  venv/Scripts/python.exe build_data.py
Then commit static/api/*.json and push -> Pages redeploys.
"""
import json
import os

import server

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(BASE_DIR, 'static', 'api')
BUILD_DAYS = 500


def main():
    os.makedirs(API_DIR, exist_ok=True)

    overview = server.get_overview(BUILD_DAYS)
    with open(os.path.join(API_DIR, 'overview.json'), 'w', encoding='utf-8') as f:
        json.dump({'data': overview, 'count': len(overview)}, f, ensure_ascii=False)

    for item in overview:
        code = item['code']
        detail = server.get_detail(code, BUILD_DAYS)
        if detail:
            with open(os.path.join(API_DIR, f'detail_{code}.json'), 'w', encoding='utf-8') as f:
                json.dump(detail, f, ensure_ascii=False)

    latest = max((it['current_date'] for it in overview), default='-')
    info = {
        'symbol_count': len(overview),
        'latest_date': latest,
        'excel_path': server.EXCEL_PATH,
    }
    with open(os.path.join(API_DIR, 'info.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)

    print(f'Built {len(overview)} symbols + overview/info JSON into static/api/')


if __name__ == '__main__':
    main()
