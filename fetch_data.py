#!/usr/bin/env python3
"""
RWA Corporate Actions Monitor — Data Fetcher
修复：Polygon 限速重试 + FMP 换用免费端点
"""

import os, json, time, requests
from datetime import datetime, timedelta, timezone

POLYGON_KEY = os.environ.get("POLYGON_KEY", "")
FMP_KEY     = os.environ.get("FMP_KEY", "")
DAYS_AHEAD  = 90

TICKERS = [
    "MU","SNDK","NVDA","TSLA","AMD","INTC","MSFT","AAPL","AMZN",
    "GOOGL","META","AVGO","MRVL","PLTR","ORCL","LLY","NBIS",
    "HOOD","CRWV","RKLB","MSTR","CRCL","HIMS","SPCX"
]

TICKER_META = {
    "MU":   {"name":"Micron",        "newIpo":False},
    "SNDK": {"name":"SanDisk",       "newIpo":False},
    "NVDA": {"name":"NVIDIA",        "newIpo":False},
    "TSLA": {"name":"Tesla",         "newIpo":False},
    "AMD":  {"name":"AMD",           "newIpo":False},
    "INTC": {"name":"Intel",         "newIpo":False},
    "MSFT": {"name":"Microsoft",     "newIpo":False},
    "AAPL": {"name":"Apple",         "newIpo":False},
    "AMZN": {"name":"Amazon",        "newIpo":False},
    "GOOGL":{"name":"Alphabet A",    "newIpo":False},
    "META": {"name":"Meta",          "newIpo":False},
    "AVGO": {"name":"Broadcom",      "newIpo":False},
    "MRVL": {"name":"Marvell",       "newIpo":False},
    "PLTR": {"name":"Palantir",      "newIpo":False},
    "ORCL": {"name":"Oracle",        "newIpo":False},
    "LLY":  {"name":"Eli Lilly",     "newIpo":False},
    "NBIS": {"name":"Nebius",        "newIpo":False},
    "HOOD": {"name":"Robinhood",     "newIpo":False},
    "CRWV": {"name":"CoreWeave",     "newIpo":True,  "ipoNote":"2025年3月IPO"},
    "RKLB": {"name":"Rocket Lab",    "newIpo":False},
    "MSTR": {"name":"MicroStrategy", "newIpo":False},
    "CRCL": {"name":"Circle",        "newIpo":True,  "ipoNote":"2025年上市"},
    "HIMS": {"name":"Hims&Hers",     "newIpo":False},
    "SPCX": {"name":"SpaceX",        "newIpo":True,  "ipoNote":"2026年6月12日上市，务必人工核查"},
}

SEC_CIK = {
    "SPCX": "1181412",
    "CRWV": "1769628",
    "SNDK": "2023554",
}

today  = datetime.now(timezone.utc).date()
future = today + timedelta(days=DAYS_AHEAD)
DATE_FROM = str(today)
DATE_TO   = str(future)

def days_left(date_str):
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d").date() - today).days
    except:
        return 9999

# ── 限速重试请求 ──────────────────────────────────────
def safe_get(url, headers=None, delay=13, retries=3):
    """Polygon 免费层每分钟5次 = 每次至少间隔12秒，这里用13秒保险"""
    for attempt in range(retries):
        time.sleep(delay)
        try:
            r = requests.get(url, headers=headers or {}, timeout=20)
            if r.status_code == 429:
                wait = 60 + attempt * 30
                print(f"  ⏳ 限速，等待{wait}秒后重试...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if "429" in str(e):
                wait = 60 + attempt * 30
                print(f"  ⏳ 限速，等待{wait}秒后重试...")
                time.sleep(wait)
                continue
            print(f"  ✗ {url[:70]}... → {e}")
            return None
        except Exception as e:
            print(f"  ✗ {url[:70]}... → {e}")
            return None
    return None

def fmp_get(url, delay=2):
    """FMP 免费层限制宽松，间隔2秒即可"""
    time.sleep(delay)
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ✗ FMP {url[:70]}... → {e}")
        return None

# ── Polygon ───────────────────────────────────────────
def poly_dividends(ticker):
    if not POLYGON_KEY: return []
    url = (f"https://api.polygon.io/v3/reference/dividends"
           f"?ticker={ticker}&ex_dividend_date.gte={DATE_FROM}"
           f"&ex_dividend_date.lte={DATE_TO}&limit=20&apiKey={POLYGON_KEY}")
    d = safe_get(url)
    if not d: return []
    result = []
    for x in d.get("results", []):
        t = x.get("dividend_type", "CD")
        result.append({
            "ticker": ticker, "source": "polygon",
            "exDate": x.get("ex_dividend_date", ""),
            "type": {"CD":"CASH","SD":"STOCK","SC":"SPECIAL"}.get(t, "CASH"),
            "declarationDate": x.get("declaration_date"),
            "recordDate":      x.get("record_date"),
            "payDate":         x.get("pay_date"),
            "cashAmount":      x.get("cash_amount"),
            "ratio": None, "splitTo": None, "splitFrom": None,
        })
    return result

def poly_splits(ticker):
    if not POLYGON_KEY: return []
    url = (f"https://api.polygon.io/v3/reference/splits"
           f"?ticker={ticker}&execution_date.gte={DATE_FROM}"
           f"&execution_date.lte={DATE_TO}&limit=10&apiKey={POLYGON_KEY}")
    d = safe_get(url)
    if not d: return []
    result = []
    for x in d.get("results", []):
        sf, st = x.get("split_from", 1), x.get("split_to", 1)
        result.append({
            "ticker": ticker, "source": "polygon",
            "exDate": x.get("execution_date", ""),
            "type": "REVERSE_SPLIT" if sf > st else "SPLIT",
            "declarationDate": None, "recordDate": None, "payDate": None,
            "cashAmount": None,
            "ratio": f"{st}:{sf}", "splitTo": st, "splitFrom": sf,
        })
    return result

# ── FMP（换用 /stable/ 端点，免费层支持）────────────────
def fmp_dividends(ticker):
    if not FMP_KEY: return []
    # 使用新版 stable 端点
    url = f"https://financialmodelingprep.com/stable/dividends-calendar?symbol={ticker}&from={DATE_FROM}&to={DATE_TO}&apikey={FMP_KEY}"
    d = fmp_get(url)
    if not d: return []
    # 也尝试旧端点格式
    if isinstance(d, dict) and "historical" in d:
        items = d["historical"]
    elif isinstance(d, list):
        items = d
    else:
        return []
    result = []
    for x in items:
        date = x.get("date") or x.get("recordDate") or ""
        if not date or not (DATE_FROM <= date <= DATE_TO):
            continue
        result.append({
            "ticker": ticker, "source": "fmp",
            "exDate": date,
            "type": "CASH",
            "declarationDate": x.get("declarationDate"),
            "recordDate":      x.get("recordDate"),
            "payDate":         x.get("paymentDate"),
            "cashAmount":      x.get("dividend") or x.get("adjDividend"),
            "ratio": None, "splitTo": None, "splitFrom": None,
        })
    return result

def fmp_splits(ticker):
    if not FMP_KEY: return []
    url = f"https://financialmodelingprep.com/stable/splits-calendar?symbol={ticker}&from={DATE_FROM}&to={DATE_TO}&apikey={FMP_KEY}"
    d = fmp_get(url)
    if not d: return []
    if isinstance(d, dict) and "historical" in d:
        items = d["historical"]
    elif isinstance(d, list):
        items = d
    else:
        return []
    result = []
    for x in items:
        date = x.get("date", "")
        if not date or not (DATE_FROM <= date <= DATE_TO):
            continue
        num = float(x.get("numerator", 1) or 1)
        den = float(x.get("denominator", 1) or 1)
        result.append({
            "ticker": ticker, "source": "fmp",
            "exDate": date,
            "type": "REVERSE_SPLIT" if den > num else "SPLIT",
            "declarationDate": None, "recordDate": None, "payDate": None,
            "cashAmount": None,
            "ratio": f"{num}:{den}", "splitTo": num, "splitFrom": den,
        })
    return result

# ── SEC EDGAR ─────────────────────────────────────────
def sec_events(ticker):
    cik = SEC_CIK.get(ticker)
    if not cik: return []
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    time.sleep(1)
    try:
        r = requests.get(url, headers={"User-Agent": "RWA-CA-Monitor contact@rwa.io"}, timeout=15)
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        print(f"  ✗ SEC {ticker}: {e}")
        return []
    filings = d.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    items = filings.get("items", [])
    accs  = filings.get("accessionNumber", [])
    docs  = filings.get("primaryDocument", [])
    result = []
    for i, form in enumerate(forms):
        if form != "8-K": continue
        date = dates[i] if i < len(dates) else ""
        if not (DATE_FROM <= date <= DATE_TO): continue
        desc = (items[i] if i < len(items) else "").lower()
        if not any(k in desc for k in ["dividend","split","distribution","8.01"]): continue
        acc_no = (accs[i] if i < len(accs) else "").replace("-", "")
        doc    = docs[i] if i < len(docs) else ""
        result.append({
            "ticker": ticker, "source": "sec_edgar",
            "exDate": date, "type": "SEC_FILING",
            "declarationDate": date, "recordDate": None, "payDate": None,
            "cashAmount": None, "ratio": None, "splitTo": None, "splitFrom": None,
            "secUrl": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no}/{doc}",
        })
    return result

# ── 交叉验证 ──────────────────────────────────────────
def merge(poly_items, fmp_items, sec_items):
    events, processed = [], set()

    def find_fmp(t, ex):  return [f for f in fmp_items  if f["ticker"]==t and f["exDate"]==ex]
    def find_poly(t, ex): return [p for p in poly_items if p["ticker"]==t and p["exDate"]==ex]
    def find_sec(t, ex):
        d = datetime.strptime(ex, "%Y-%m-%d").date() if ex else today
        return [s for s in sec_items if s["ticker"]==t
                and abs((datetime.strptime(s["exDate"],"%Y-%m-%d").date()-d).days)<=5]

    def make(base, fmp_ref, sec_ref):
        conflicts = []
        if fmp_ref and base.get("cashAmount") and fmp_ref.get("cashAmount"):
            if abs(float(base["cashAmount"]) - float(fmp_ref["cashAmount"])) > 0.001:
                conflicts.append({"field":"金额","poly":f'${base["cashAmount"]}','fmp':f'${fmp_ref["cashAmount"]}'})
        if fmp_ref and base.get("ratio") and fmp_ref.get("ratio") and base["ratio"] != fmp_ref["ratio"]:
            conflicts.append({"field":"比例","poly":base["ratio"],"fmp":fmp_ref["ratio"]})
        n = 1 + (1 if fmp_ref else 0) + (1 if sec_ref else 0)
        conf = "conflict" if conflicts else "confirmed_3" if n>=3 else "confirmed_2" if n==2 else "single"
        meta = TICKER_META.get(base["ticker"], {})
        return {
            "ticker":          base["ticker"],
            "exDate":          base["exDate"],
            "type":            base["type"],
            "typeLabel":       {"CASH":"现金分红","STOCK":"股票分红","SPLIT":"拆股",
                                "REVERSE_SPLIT":"合股(缩股)","SPECIAL":"特别分红",
                                "SEC_FILING":"SEC 8-K公告"}.get(base["type"], base["type"]),
            "declarationDate": base.get("declarationDate") or (fmp_ref or {}).get("declarationDate") or "—",
            "recordDate":      base.get("recordDate")      or (fmp_ref or {}).get("recordDate")      or "—",
            "payDate":         base.get("payDate")         or (fmp_ref or {}).get("payDate")         or "—",
            "cashAmount":      base.get("cashAmount")      or (fmp_ref or {}).get("cashAmount"),
            "ratio":           base.get("ratio")           or (fmp_ref or {}).get("ratio"),
            "splitTo":   base.get("splitTo"),
            "splitFrom": base.get("splitFrom"),
            "confidence":  conf,
            "conflicts":   conflicts,
            "sourcePoly":  base["source"] == "polygon",
            "sourceFmp":   bool(fmp_ref),
            "sourceSec":   bool(sec_ref),
            "secUrl":      (sec_ref or {}).get("secUrl"),
            "isNewTicker": meta.get("newIpo", False),
            "ipoNote":     meta.get("ipoNote", ""),
            "daysLeft":    days_left(base["exDate"]),
        }

    for p in poly_items:
        k = f"{p['ticker']}_{p['exDate']}_{p['type']}"
        if k in processed: continue
        processed.add(k)
        fm = find_fmp(p["ticker"], p["exDate"])
        sc = find_sec(p["ticker"], p["exDate"])
        events.append(make(p, fm[0] if fm else None, sc[0] if sc else None))

    for f in fmp_items:
        if find_poly(f["ticker"], f["exDate"]): continue
        k = f"{f['ticker']}_{f['exDate']}_fmp"
        if k in processed: continue
        processed.add(k)
        sc = find_sec(f["ticker"], f["exDate"])
        events.append(make(f, None, sc[0] if sc else None))

    for s in sec_items:
        if find_poly(s["ticker"], s["exDate"]) or find_fmp(s["ticker"], s["exDate"]): continue
        k = f"{s['ticker']}_{s['exDate']}_sec"
        if k in processed: continue
        processed.add(k)
        events.append(make(s, None, None))

    return sorted(events, key=lambda e: e["exDate"])

# ── 主流程 ────────────────────────────────────────────
def main():
    print(f"开始拉取数据 | 范围: {DATE_FROM} ~ {DATE_TO}")
    print(f"Polygon Key: {'✓' if POLYGON_KEY else '✗ 未配置'}")
    print(f"FMP Key:     {'✓' if FMP_KEY else '✗ 未配置'}")
    print(f"注意：Polygon 免费层限速，每个请求间隔13秒，预计耗时约10分钟")

    poly_all, fmp_all, sec_all = [], [], []

    for i, ticker in enumerate(TICKERS):
        print(f"[{i+1:02d}/{len(TICKERS)}] {ticker}")
        # Polygon: 每次请求间隔13秒（内置在safe_get里）
        poly_all += poly_dividends(ticker)
        poly_all += poly_splits(ticker)
        # FMP: 新端点，间隔2秒
        fmp_all  += fmp_dividends(ticker)
        fmp_all  += fmp_splits(ticker)
        # SEC EDGAR
        if ticker in SEC_CIK:
            sec_all += sec_events(ticker)

    events = merge(poly_all, fmp_all, sec_all)
    conflicts = [e for e in events if e["confidence"] == "conflict"]
    urgent    = [e for e in events if 0 <= e["daysLeft"] <= 7]
    new_evs   = [e for e in events if e["isNewTicker"]]

    output = {
        "updatedAt":    datetime.now(timezone.utc).isoformat(),
        "updatedAtCST": (datetime.now(timezone.utc)+timedelta(hours=8)).strftime("%Y-%m-%d %H:%M CST"),
        "dateFrom":     DATE_FROM,
        "dateTo":       DATE_TO,
        "totalTickers": len(TICKERS),
        "stats": {
            "total":      len(events),
            "confirmed3": len([e for e in events if e["confidence"]=="confirmed_3"]),
            "confirmed2": len([e for e in events if e["confidence"]=="confirmed_2"]),
            "single":     len([e for e in events if e["confidence"]=="single"]),
            "conflict":   len(conflicts),
            "urgent7d":   len(urgent),
        },
        "alerts": {
            "conflicts":  [{"ticker":e["ticker"],"exDate":e["exDate"],"type":e["typeLabel"],"conflicts":e["conflicts"]} for e in conflicts],
            "urgent":     [{"ticker":e["ticker"],"exDate":e["exDate"],"type":e["typeLabel"],"daysLeft":e["daysLeft"]} for e in urgent],
            "newTickers": [{"ticker":e["ticker"],"ipoNote":e["ipoNote"]} for e in new_evs],
        },
        "events": events,
        "tickerMeta": TICKER_META,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成 | 共 {len(events)} 个事件 | 冲突: {len(conflicts)} | 7天内: {len(urgent)}")
    if conflicts: print("⚠ 冲突标的:", [e["ticker"] for e in conflicts])
    if urgent:    print("⚠ 7天内到期:", [f"{e['ticker']}({e['exDate']})" for e in urgent])

if __name__ == "__main__":
    main()
