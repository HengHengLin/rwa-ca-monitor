#!/usr/bin/env python3
"""
RWA Corporate Actions Monitor — Data Fetcher v3
- 只用 Polygon 作为主数据源（FMP免费层不支持按ticker查，数据不可靠，已禁用）
- Polygon 免费层限速：每分钟5次，每请求间隔13秒
- SEC EDGAR 作为新上市标的兜底
"""

import os, json, time, requests
from datetime import datetime, timedelta, timezone

POLYGON_KEY = os.environ.get("POLYGON_KEY", "")
DAYS_AHEAD  = 90

TICKERS = [
    "MU","SNDK","NVDA","TSLA","AMD","INTC","MSFT","AAPL","AMZN",
    "GOOGL","META","AVGO","MRVL","PLTR","ORCL","LLY","NBIS",
    "HOOD","CRWV","RKLB","MSTR","CRCL","HIMS","SPCX","COIN",
    "SOXL","EWY","QQQ","DRAM","CBRS"
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
    "CRWV": {"name":"CoreWeave",     "newIpo":True,  "ipoNote":"2025年3月IPO，数据可能不完整"},
    "RKLB": {"name":"Rocket Lab",    "newIpo":False},
    "MSTR": {"name":"MicroStrategy", "newIpo":False},
    "CRCL": {"name":"Circle",        "newIpo":True,  "ipoNote":"2025年上市，需人工复核"},
    "HIMS": {"name":"Hims&Hers",     "newIpo":False},
    "SPCX": {"name":"SpaceX",        "newIpo":True,  "ipoNote":"2026年6月12日上市，API尚未收录，务必人工核查"},
    "COIN": {"name":"Coinbase",       "newIpo":False},
    "SOXL": {"name":"Direxion 3x半导体ETF", "newIpo":False},
    "EWY":  {"name":"iShares韩国ETF", "newIpo":False},
    "QQQ":  {"name":"Invesco QQQ",    "newIpo":False},
    "DRAM": {"name":"Roundhill DRAM ETF","newIpo":False},
    "CBRS": {"name":"Cerebras",       "newIpo":True, "ipoNote":"2024年上市，较新标的"},
}

# SEC EDGAR CIK（只对新上市/特殊标的）
SEC_CIK = {
    "SPCX": "1181412",
    "CRWV": "1769628",
    "SNDK": "2023554",
}

today    = datetime.now(timezone.utc).date()
future   = today + timedelta(days=DAYS_AHEAD)
DATE_FROM = str(today)
DATE_TO   = str(future)

def days_left(date_str):
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d").date() - today).days
    except:
        return 9999

# ── Polygon 限速请求（每次间隔13秒，429时等60秒重试）────
def poly_get(url, retries=3):
    for attempt in range(retries):
        time.sleep(13)  # 免费层每分钟5次 = 每次至少12秒
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 429:
                wait = 65 + attempt * 30
                print(f"    ⏳ 限速429，等待{wait}秒...")
                time.sleep(wait)
                continue
            if r.status_code == 403:
                print(f"    ✗ 403 权限不足，跳过")
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"    ✗ {e}")
            return None
    return None

def poly_dividends(ticker):
    if not POLYGON_KEY: return []
    url = (f"https://api.polygon.io/v3/reference/dividends"
           f"?ticker={ticker}&ex_dividend_date.gte={DATE_FROM}"
           f"&ex_dividend_date.lte={DATE_TO}&limit=20&apiKey={POLYGON_KEY}")
    d = poly_get(url)
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
    d = poly_get(url)
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

# ── SEC EDGAR（仅新上市标的，无需Key）──────────────────
def sec_events(ticker):
    cik = SEC_CIK.get(ticker)
    if not cik: return []
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    time.sleep(1)
    try:
        r = requests.get(url, headers={"User-Agent":"RWA-CA-Monitor contact@rwa.io"}, timeout=15)
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        print(f"    ✗ SEC {ticker}: {e}")
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
        acc_no = (accs[i] if i < len(accs) else "").replace("-","")
        doc = docs[i] if i < len(docs) else ""
        result.append({
            "ticker": ticker, "source": "sec_edgar",
            "exDate": date, "type": "SEC_FILING",
            "declarationDate": date, "recordDate": None, "payDate": None,
            "cashAmount": None, "ratio": None, "splitTo": None, "splitFrom": None,
            "secUrl": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no}/{doc}",
        })
    return result

# ── 整理事件 ──────────────────────────────────────────
def build_event(item, sec_ref=None):
    meta = TICKER_META.get(item["ticker"], {})
    # 单源（Polygon），但可用SEC做补充验证
    has_sec = bool(sec_ref)
    confidence = "confirmed_2" if has_sec else "single"
    return {
        "ticker":          item["ticker"],
        "exDate":          item["exDate"],
        "type":            item["type"],
        "typeLabel":       {"CASH":"现金分红","STOCK":"股票分红","SPLIT":"拆股",
                            "REVERSE_SPLIT":"合股(缩股)","SPECIAL":"特别分红",
                            "SEC_FILING":"SEC 8-K公告"}.get(item["type"], item["type"]),
        "declarationDate": item.get("declarationDate") or "—",
        "recordDate":      item.get("recordDate") or "—",
        "payDate":         item.get("payDate") or "—",
        "cashAmount":      item.get("cashAmount"),
        "ratio":           item.get("ratio"),
        "splitTo":         item.get("splitTo"),
        "splitFrom":       item.get("splitFrom"),
        "confidence":      confidence,
        "conflicts":       [],
        "sourcePoly":      item["source"] == "polygon",
        "sourceFmp":       False,
        "sourceSec":       has_sec,
        "secUrl":          sec_ref.get("secUrl") if sec_ref else None,
        "isNewTicker":     meta.get("newIpo", False),
        "ipoNote":         meta.get("ipoNote", ""),
        "daysLeft":        days_left(item["exDate"]),
    }

def merge(poly_items, sec_items):
    events, processed = [], set()

    def find_sec(ticker, ex):
        try:
            d = datetime.strptime(ex, "%Y-%m-%d").date()
            return next((s for s in sec_items
                         if s["ticker"]==ticker
                         and abs((datetime.strptime(s["exDate"],"%Y-%m-%d").date()-d).days)<=5), None)
        except:
            return None

    for p in poly_items:
        k = f"{p['ticker']}_{p['exDate']}_{p['type']}"
        if k in processed: continue
        processed.add(k)
        sec_ref = find_sec(p["ticker"], p["exDate"])
        events.append(build_event(p, sec_ref))

    # SEC-only（Polygon没有的新上市标的）
    for s in sec_items:
        poly_match = any(p["ticker"]==s["ticker"] and p["exDate"]==s["exDate"] for p in poly_items)
        if poly_match: continue
        k = f"{s['ticker']}_{s['exDate']}_sec"
        if k in processed: continue
        processed.add(k)
        events.append(build_event(s))

    return sorted(events, key=lambda e: e["exDate"])

# ── 主流程 ────────────────────────────────────────────
def main():
    print(f"开始拉取数据 | 范围: {DATE_FROM} ~ {DATE_TO}")
    print(f"Polygon Key: {'✓' if POLYGON_KEY else '✗ 未配置'}")
    print(f"数据源：仅 Polygon + SEC EDGAR（FMP已禁用，免费层不支持按ticker查询）")
    print(f"预计耗时：约13分钟（Polygon限速，每请求间隔13秒）\n")

    poly_all, sec_all = [], []

    for i, ticker in enumerate(TICKERS):
        print(f"[{i+1:02d}/{len(TICKERS)}] {ticker}")
        divs = poly_dividends(ticker)
        splits = poly_splits(ticker)
        poly_all += divs + splits
        if divs or splits:
            print(f"    ✓ Polygon: {len(divs)}条分红, {len(splits)}条拆股")
        if ticker in SEC_CIK:
            sec = sec_events(ticker)
            sec_all += sec
            if sec:
                print(f"    ✓ SEC: {len(sec)}条8-K公告")

    events = merge(poly_all, sec_all)
    urgent = [e for e in events if 0 <= e["daysLeft"] <= 7]
    new_evs = [e for e in events if e["isNewTicker"]]

    output = {
        "updatedAt":    datetime.now(timezone.utc).isoformat(),
        "updatedAtCST": (datetime.now(timezone.utc)+timedelta(hours=8)).strftime("%Y-%m-%d %H:%M CST"),
        "dateFrom":  DATE_FROM,
        "dateTo":    DATE_TO,
        "totalTickers": len(TICKERS),
        "dataNote": "数据来源：Polygon（主）+ SEC EDGAR（新上市兜底）。FMP免费层不支持按ticker查询已禁用。",
        "stats": {
            "total":      len(events),
            "confirmed2": len([e for e in events if e["confidence"]=="confirmed_2"]),
            "single":     len([e for e in events if e["confidence"]=="single"]),
            "conflict":   0,
            "urgent7d":   len(urgent),
        },
        "alerts": {
            "conflicts":  [],
            "urgent":     [{"ticker":e["ticker"],"exDate":e["exDate"],"type":e["typeLabel"],"daysLeft":e["daysLeft"]} for e in urgent],
            "newTickers": [{"ticker":e["ticker"],"ipoNote":e["ipoNote"]} for e in new_evs],
        },
        "events": events,
        "tickerMeta": TICKER_META,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成 | 共 {len(events)} 个事件 | 7天内: {len(urgent)}")
    if urgent:
        print("⚠ 7天内到期:", [f"{e['ticker']}({e['exDate']})" for e in urgent])

if __name__ == "__main__":
    main()
