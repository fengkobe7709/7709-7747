import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HK_TZ = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "history.db"

PRODUCTS = {
    "7709": {
        "code": "7709",
        "name": "CSOP SK Hynix Daily (2x)",
        "url": "https://www.csopasset.com/en/products/hk-skhy-2l",
    },
    "7747": {
        "code": "7747",
        "name": "CSOP Samsung Electronics Daily (2x)",
        "url": "https://www.csopasset.com/en/products/hk-smsn-2l",
    },
}

app = FastAPI(title="CSOP Premium Monitor")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                ts TEXT NOT NULL,
                price REAL,
                inav REAL,
                premium REAL,
                price_time TEXT,
                inav_time TEXT,
                source_url TEXT,
                raw_status TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_code_ts ON snapshots(code, ts)")


def hk_now_iso() -> str:
    return datetime.now(HK_TZ).isoformat(timespec="seconds")


def number_after(label_pattern: str, text: str) -> Optional[float]:
    # Look near a label for HKD/USD amount. Works with most CSOP page text variants.
    m = re.search(label_pattern + r".{0,500}?\b(?:HKD|USD)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", text, re.I | re.S)
    if m:
        return float(m.group(1))
    return None


def time_after(label_pattern: str, text: str) -> Optional[str]:
    m = re.search(label_pattern + r".{0,500}?Time\s*[:：]?\s*([0-9]{1,2}:[0-9]{2}\s*(?:AM|PM)?)", text, re.I | re.S)
    if m:
        return m.group(1).strip()
    return None


def compact_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def extract_from_json_like(html: str) -> Dict[str, Any]:
    # CSOP may render values from embedded JS. This scans raw HTML/scripts too.
    raw = re.sub(r"\\u002F", "/", html)
    result: Dict[str, Any] = {}

    patterns = [
        ("inav", r"(?:Estimated NAV per Unit|intra[- ]day estimated nav|iNAV|navPerUnit)[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)"),
        ("price", r"(?:Intra[- ]day Market Price|marketPrice|Market Price)[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)"),
    ]
    for key, pat in patterns:
        for m in re.finditer(pat, raw, re.I | re.S):
            try:
                val = float(m.group(1))
                if 0 < val < 100000:
                    result[key] = val
                    break
            except Exception:
                pass
    return result


def fetch_product(code: str) -> Dict[str, Any]:
    p = PRODUCTS[code]
    headers = {
        "User-Agent": "Mozilla/5.0 CSOPPremiumMonitor/1.0",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    }
    try:
        r = requests.get(p["url"], headers=headers, timeout=15)
        r.raise_for_status()
        html = r.text
        text = compact_text(html)
        json_guess = extract_from_json_like(html)

        inav = number_after(r"Intra[- ]day Estimated NAV per Unit", text) or json_guess.get("inav")
        price = number_after(r"Intra[- ]day Market Price", text) or json_guess.get("price")
        inav_time = time_after(r"Intra[- ]day Estimated NAV per Unit", text)
        price_time = time_after(r"Intra[- ]day Market Price", text)

        premium = None
        if price is not None and inav not in (None, 0):
            premium = (price / inav - 1) * 100

        status = "ok" if price is not None and inav is not None else "partial"
        return {
            **p,
            "ts": hk_now_iso(),
            "price": price,
            "inav": inav,
            "premium": premium,
            "price_time": price_time,
            "inav_time": inav_time,
            "status": status,
            "note": "Market Price on CSOP may be delayed; iNAV and market price can have different timestamps.",
        }
    except Exception as e:
        return {**p, "ts": hk_now_iso(), "price": None, "inav": None, "premium": None, "price_time": None, "inav_time": None, "status": "error", "error": str(e)}


def save_snapshot(item: Dict[str, Any]) -> None:
    if item.get("price") is None and item.get("inav") is None:
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO snapshots(code, ts, price, inav, premium, price_time, inav_time, source_url, raw_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["code"], item["ts"], item.get("price"), item.get("inav"), item.get("premium"),
                item.get("price_time"), item.get("inav_time"), item.get("url"), item.get("status"),
            ),
        )


def get_history(code: str, limit: int = 300) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ts, price, inav, premium FROM snapshots WHERE code=? ORDER BY id DESC LIMIT ?",
            (code, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/snapshot")
def snapshot():
    init_db()
    data = []
    for code in PRODUCTS:
        item = fetch_product(code)
        save_snapshot(item)
        item["history"] = get_history(code)
        data.append(item)
    return {"updated_at": hk_now_iso(), "products": data}


@app.get("/healthz")
def healthz():
    return {"ok": True, "time": hk_now_iso()}
