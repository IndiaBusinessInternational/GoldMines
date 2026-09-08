#!/usr/bin/env python3
"""IBI Gold Mines - daily data pipeline (stdlib only, runs in GitHub Actions).

Builds data/history.json from three public sources:
  1. Yahoo Finance  GC=F  (COMEX gold, USD/troy oz)  - 10 years of daily closes
  2. Frankfurter    USD->INR (ECB reference rate)     - daily, forward-filled
  3. IBJA           ibjarates.com AM/PM tables         - the official Indian
                    benchmark, INR per 10 g, accumulated run over run

The front end derives every INR figure itself (duty schedule, GST, city
premium); this file stays raw so the maths lives in exactly one place.
"""
import json, re, sys, os, datetime as dt, urllib.request

PIPELINE_VERSION = 'v1.1.1'   # must match APP_VERSION in index.html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, 'data', 'history.json')
UA   = 'Mozilla/5.0 (compatible; IBI-GoldMines-data/1.0; +https://gold.indiabusinessinternational.online)'

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')

def fetch_gold():
    """[[iso_date, close_usd_per_oz], ...] oldest -> newest, 10y daily.

    SETTLED SESSIONS ONLY. Both scheduled runs (07:30 and 12:30 UTC) fire while
    the COMEX session dated today is still trading, so Yahoo's last bar is an
    in-progress print, not a close. Storing it corrupts the series: the 4 Sep
    2026 run captured 4488.9 at 16:29 UTC when that session actually closed at
    4429.8, an error of 1.33% that then fed the day-change on the page. Today's
    price belongs to the live feed, not to the history.
    """
    j = json.loads(get('https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range=10y&interval=1d'))
    res = j['chart']['result'][0]
    ts  = res['timestamp']
    cl  = res['indicators']['quote'][0]['close']
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    out = []
    for t, c in zip(ts, cl):
        if c is None: continue
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()
        if d >= today: continue
        if out and out[-1][0] == d: out[-1][1] = round(float(c), 2)
        else: out.append([d, round(float(c), 2)])
    return out


# NOTE — do not "correct" the live spot onto the futures curve.
# On 7 Sep 2026 (US Labor Day) Yahoo's GC=F sat frozen at a pre-holiday 4476.6
# while spot traded down to 4393.2, a 1.9% gap that looks exactly like a
# term-structure basis and is not one. Converting by it would have priced the
# page 1.96% ABOVE the Indian benchmark. The check that settles it: IBJA's live
# 999 rate divided by the spot-derived landed price is 1.0778, and the
# calibration factor taken from the futures history is 1.0784. They agree to
# 0.06%, so the two dollar legs sit at the same level and the existing
# spot-fed calculation is right.

def fetch_inr(start):
    j = json.loads(get(f'https://api.frankfurter.dev/v1/{start}..?from=USD&to=INR'))
    rates = j['rates']
    return sorted([[d, float(v['INR'])] for d, v in rates.items()])

IBJA_ROW = re.compile(r'(\d{2}/\d{2}/\d{4})((?:\s+[\d,]+){7})')
def fetch_ibja():
    """Returns {'am': {iso: [g999,g995,g916,g750,g585,ag999,pt999]}, 'pm': {...}}  (INR per 10 g)."""
    html = get('https://ibjarates.com/')
    tables = re.findall(r'<table[^>]*>.*?</table>', html, re.S)
    parsed = []
    for t in tables:
        txt = re.sub(r'<[^>]+>', ' ', t); txt = re.sub(r'\s+', ' ', txt)
        rows = {}
        for m in IBJA_ROW.finditer(txt):
            d, m2, y = m.group(1).split('/')
            iso = f'{y}-{m2}-{d}'
            nums = [int(x.replace(',', '')) for x in m.group(2).split()]
            rows[iso] = nums
        if rows: parsed.append(rows)
    # The page lists the AM table first, then the PM table.
    out = {'am': {}, 'pm': {}}
    if len(parsed) >= 1: out['am'] = parsed[0]
    if len(parsed) >= 2: out['pm'] = parsed[1]
    # Live "today" spot boxes (per gram) - present only once the day's rate is up.
    m999 = re.search(r'id="GoldRatesCompare999"[^>]*>\s*([\d,]+)', html)
    m916 = re.search(r'id="GoldRatesCompare916"[^>]*>\s*([\d,]+)', html)
    out['today_per_g'] = {
        '999': int(m999.group(1).replace(',', '')) if m999 else None,
        '916': int(m916.group(1).replace(',', '')) if m916 else None,
    }
    return out

def main():
    prev = {}
    if os.path.exists(OUT):
        try: prev = json.load(open(OUT, encoding='utf-8'))
        except Exception: prev = {}

    errors = []
    gold = prev.get('xauusd', [])
    try:
        fresh = fetch_gold()
        # Merge by date: Yahoo occasionally omits a completed session on one call and
        # returns it on the next (3 Sep 2026 vanished between two runs an hour apart).
        # Keep every date we have ever seen; fresh values overwrite by date.
        merged = {d: v for d, v in gold}
        merged.update({d: v for d, v in fresh})
        cutoff = fresh[0][0] if fresh else None
        gold = sorted([[d, v] for d, v in merged.items() if cutoff is None or d >= cutoff])
    except Exception as e: errors.append(f'gold: {e}')

    inr = prev.get('usdinr', [])
    try:
        start = gold[0][0] if gold else (dt.date.today() - dt.timedelta(days=3660)).isoformat()
        fresh = fetch_inr(start)
        merged = {d: v for d, v in inr}
        merged.update({d: v for d, v in fresh})
        inr = sorted([[d, v] for d, v in merged.items() if d >= start])
    except Exception as e: errors.append(f'inr: {e}')

    ibja_prev = prev.get('ibja', {'am': {}, 'pm': {}})
    ibja = {'am': dict(ibja_prev.get('am', {})), 'pm': dict(ibja_prev.get('pm', {}))}
    today_per_g = prev.get('ibja_today', None)
    try:
        fresh = fetch_ibja()
        ibja['am'].update(fresh['am']); ibja['pm'].update(fresh['pm'])
        if fresh['today_per_g']['999']:
            # This box is IBJA's LIVE rate, not a session fixing, so the read time
            # is the right stamp. It is only ever misleading when the file itself
            # is stale, which the page now says out loud rather than implying the
            # live price has drifted from the benchmark.
            today_per_g = {'date': dt.date.today().isoformat(),
                           'at': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                           **fresh['today_per_g']}
    except Exception as e: errors.append(f'ibja: {e}')

    if not gold or not inr:
        print('FATAL: no price series', errors); sys.exit(1)

    doc = {
        'schema': 2,
        'pipeline_version': PIPELINE_VERSION,
        'updated': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'sources': {
            'xauusd': 'Yahoo Finance GC=F (COMEX gold futures front month), USD per troy ounce, settled daily closes only',
            'usdinr': 'Frankfurter (ECB reference rate), INR per USD, daily',
            'ibja':   'India Bullion and Jewellers Association, ibjarates.com, INR per 10 g, AM/PM; columns 999,995,916,750,585,silver999,platinum999',
        },
        'xauusd': gold,
        'usdinr': inr,
        'ibja': {'am': dict(sorted(ibja['am'].items())), 'pm': dict(sorted(ibja['pm'].items()))},
        'ibja_today': today_per_g,
        'errors': errors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'), ensure_ascii=False)
    os.replace(tmp, OUT)
    t = today_per_g or {}
    print(f'ok: gold {len(gold)} pts ({gold[0][0]}..{gold[-1][0]}), inr {len(inr)} pts, '
          f'ibja am {len(doc["ibja"]["am"])} / pm {len(doc["ibja"]["pm"])} days, '
          f'ibja live 999={t.get("999")} 916={t.get("916")} read {t.get("at")}, '
          f'errors={errors}')

if __name__ == '__main__':
    main()
