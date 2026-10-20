#!/usr/bin/env python3
"""Mengumpulkan data intermarket dari sumber gratis.

Keluaran:
  data/latest.json   angka terbaru, perubahan, sparkline, dan sinyal
  data/history.json  riwayat harian (+-14 bulan) per instrumen

Sumber:
  yfinance  harga saham, indeks, valas, komoditas, kripto (tidak resmi, bisa berubah)
  FRED      UST 2 tahun, kurva 10y-2y, spread kredit HY (tanpa API key, jeda 1 hari)

Pakai --demo untuk data sintetis (uji tampilan tanpa internet).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import random
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WIB = timezone(timedelta(hours=7))

# (id, nama, grup, sumber, simbol, jenis)
# jenis: price = perubahan dalam %, yield = level dalam %, perubahan dalam bp
ASSETS = [
    ("jkse", "IHSG", "Indonesia", "yf", "^JKSE", "price"),
    ("eido", "EIDO (ETF MSCI Indonesia, AS)", "Indonesia", "yf", "EIDO", "price"),
    ("usdidr", "USD/IDR", "Indonesia", "yf", "USDIDR=X", "price"),
    ("spx", "S&P 500", "Saham global", "yf", "^GSPC", "price"),
    ("ndx", "Nasdaq Composite", "Saham global", "yf", "^IXIC", "price"),
    ("dji", "Dow Jones", "Saham global", "yf", "^DJI", "price"),
    ("dax", "DAX", "Saham global", "yf", "^GDAXI", "price"),
    ("n225", "Nikkei 225", "Saham global", "yf", "^N225", "price"),
    ("hsi", "Hang Seng", "Saham global", "yf", "^HSI", "price"),
    ("ssec", "Shanghai Composite", "Saham global", "yf", "000001.SS", "price"),
    ("kospi", "Kospi", "Saham global", "yf", "^KS11", "price"),
    ("us10y", "UST 10 tahun (%)", "Suku bunga & kredit", "yf", "^TNX", "yield"),
    ("us5y", "UST 5 tahun (%)", "Suku bunga & kredit", "yf", "^FVX", "yield"),
    ("us2y", "UST 2 tahun (%)", "Suku bunga & kredit", "fred", "DGS2", "yield"),
    ("curve", "Kurva 10y-2y (%)", "Suku bunga & kredit", "fred", "T10Y2Y", "yield"),
    ("hyoas", "Spread kredit HY (%)", "Suku bunga & kredit", "fred", "BAMLH0A0HYM2", "yield"),
    ("dxy", "Indeks dolar (DXY)", "Valas", "yf", "DX-Y.NYB", "price"),
    ("eurusd", "EUR/USD", "Valas", "yf", "EURUSD=X", "price"),
    ("usdjpy", "USD/JPY", "Valas", "yf", "USDJPY=X", "price"),
    ("audusd", "AUD/USD", "Valas", "yf", "AUDUSD=X", "price"),
    ("gold", "Emas (US$/oz)", "Komoditas", "yf", "GC=F", "price"),
    ("silver", "Perak (US$/oz)", "Komoditas", "yf", "SI=F", "price"),
    ("copper", "Tembaga (US$/lb)", "Komoditas", "yf", "HG=F", "price"),
    ("wti", "Minyak WTI (US$)", "Komoditas", "yf", "CL=F", "price"),
    ("brent", "Minyak Brent (US$)", "Komoditas", "yf", "BZ=F", "price"),
    ("btc", "Bitcoin (US$)", "Kripto & volatilitas", "yf", "BTC-USD", "price"),
    ("eth", "Ethereum (US$)", "Kripto & volatilitas", "yf", "ETH-USD", "price"),
    ("vix", "VIX", "Kripto & volatilitas", "yf", "^VIX", "price"),
]

DP = {  # jumlah desimal tampilan
    "jkse": 0, "eido": 2, "usdidr": 0, "spx": 0, "ndx": 0, "dji": 0, "dax": 0,
    "n225": 0, "hsi": 0, "ssec": 0, "kospi": 0, "us10y": 3, "us5y": 3, "us2y": 2,
    "curve": 2, "hyoas": 2, "dxy": 2, "eurusd": 4, "usdjpy": 2, "audusd": 4,
    "gold": 0, "silver": 2, "copper": 3, "wti": 2, "brent": 2, "btc": 0, "eth": 0,
    "vix": 2,
}

DEMO_START = {
    "jkse": 5185, "eido": 18, "usdidr": 18027, "spx": 7659, "ndx": 26140, "dji": 52002,
    "dax": 24500, "n225": 64855, "hsi": 27000, "ssec": 3722, "kospi": 5700,
    "us10y": 5.10, "us5y": 4.95, "us2y": 4.70, "curve": 0.40, "hyoas": 3.2,
    "dxy": 99, "eurusd": 1.1231, "usdjpy": 158.1, "audusd": 0.66, "gold": 4190,
    "silver": 57.7, "copper": 5.2, "wti": 101, "brent": 108, "btc": 82500,
    "eth": 2425, "vix": 20,
}


# ---------------------------------------------------------------- pengambilan
def fetch_yf(symbol: str, tries: int = 3):
    import yfinance as yf

    last_err = None
    for i in range(tries):
        try:
            df = yf.Ticker(symbol).history(period="14mo", interval="1d", auto_adjust=False)
            s = df["Close"].dropna()
            if len(s) > 30:
                return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in s.items()]
            last_err = "data terlalu sedikit"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"yfinance {symbol}: {last_err}")


def fetch_fred(series_id: str, tries: int = 3):
    start = (datetime.now(timezone.utc) - timedelta(days=430)).strftime("%Y-%m-%d")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    last_err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 intermarket-dashboard"})
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode("utf-8")
            out = []
            for row in csv.DictReader(io.StringIO(text)):
                key = [k for k in row if k.lower() != "observation_date" and k.lower() != "date"][0]
                val = row[key]
                if val not in ("", "."):
                    out.append((row.get("observation_date") or row.get("DATE"), float(val)))
            if len(out) > 30:
                return out
            last_err = "data terlalu sedikit"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"FRED {series_id}: {last_err}")


def demo_series(asset_id: str, n: int = 300):
    rnd = random.Random(hash(asset_id) % 10_000)
    end = DEMO_START[asset_id]
    kind = next(a[5] for a in ASSETS if a[0] == asset_id)
    vol = 0.011 if kind == "price" else 0.004
    if asset_id in ("vix",):
        vol = 0.05
    if asset_id in ("btc", "eth"):
        vol = 0.025
    walk = [1.0]
    for _ in range(n - 1):
        walk.append(walk[-1] * (1 + rnd.gauss(0, vol)) if kind == "price" else walk[-1] + rnd.gauss(0, vol * 3))
    scale = end / walk[-1] if kind == "price" else 1
    shift = end - walk[-1] if kind == "yield" else 0
    day = datetime.now(WIB).date()
    dates = []
    while len(dates) < n:
        if day.weekday() < 5:
            dates.append(day.strftime("%Y-%m-%d"))
        day -= timedelta(days=1)
    dates.reverse()
    return [(d, w * scale + shift) for d, w in zip(dates, walk)]


# ------------------------------------------------------------------- hitungan
def metrics(series, kind):
    dates = [x[0] for x in series]
    vals = [x[1] for x in series]
    last = vals[-1]

    def ch(n):
        if len(vals) <= n:
            return None
        a = vals[-1 - n]
        if kind == "yield":
            return round((last - a) * 100, 1)
        return round((last / a - 1) * 100, 2) if a else None

    year = dates[-1][:4]
    base = None
    for d, v in series:
        if d[:4] == year:
            break
        base = v
    if base is None:
        ytd = None
    elif kind == "yield":
        ytd = round((last - base) * 100, 1)
    else:
        ytd = round((last / base - 1) * 100, 2)
    return {
        "last": round(last, 4),
        "date": dates[-1],
        "d1": ch(1), "d5": ch(5), "d21": ch(21), "ytd": ytd,
        "spark": [round(v, 4) for v in vals[-60:]],
    }


def build_signals(hist):
    """Aturan sederhana dan transparan. Bukan prediksi."""

    def vals(i):
        return hist[i]["v"] if i in hist else None

    def pct(i, n):
        v = vals(i)
        return (v[-1] / v[-1 - n] - 1) * 100 if v and len(v) > n else None

    def bp(i, n):
        v = vals(i)
        return (v[-1] - v[-1 - n]) * 100 if v and len(v) > n else None

    out = []

    def add(key, label, state, text, rule):
        out.append({"id": key, "label": label, "state": state, "text": text, "rule": rule})

    v = vals("vix")
    if v:
        x = v[-1]
        st = "dukung" if x < 16 else "netral" if x < 22 else "waspada" if x < 28 else "tekanan"
        add("vix", "Volatilitas", st, f"VIX {x:.1f}, 1 hari {pct('vix', 1):+.1f}%",
            "Di bawah 16 mendukung, 16-22 netral, 22-28 waspada, di atas 28 tekanan")

    b = bp("us10y", 5)
    if b is not None:
        lvl = vals("us10y")[-1]
        st = "tekanan" if b > 15 else "dukung" if b < -15 else "netral"
        if st == "netral" and lvl >= 5:
            st = "waspada"
        add("rates", "Suku bunga", st, f"UST 10 tahun {lvl:.2f}%, 5 hari {b:+.0f} bp",
            "Naik lebih dari 15 bp dalam 5 hari tekanan, turun lebih dari 15 bp mendukung, level di atas 5% waspada")

    p = pct("dxy", 5)
    if p is not None:
        st = "tekanan" if p > 1 else "dukung" if p < -1 else "netral"
        add("usd", "Dolar", st, f"DXY {vals('dxy')[-1]:.2f}, 5 hari {p:+.2f}%",
            "Menguat lebih dari 1% dalam 5 hari menekan aset berisiko dan pasar berkembang; melemah lebih dari 1% mendukung")

    c = vals("curve")
    if c:
        x = c[-1]
        st = "waspada" if x < 0 else "netral"
        add("curve", "Kurva imbal hasil", st, f"10y-2y {x:+.2f} poin persen",
            "Negatif (terbalik) waspada, selain itu netral")

    h = vals("hyoas")
    if h and len(h) > 20:
        x, d20 = h[-1], (h[-1] - h[-21]) * 100
        st = "tekanan" if d20 > 40 else "waspada" if d20 > 20 else "netral"
        add("credit", "Kredit", st, f"Spread HY {x:.2f}%, 20 hari {d20:+.0f} bp",
            "Melebar lebih dari 40 bp dalam 20 hari tekanan, lebih dari 20 bp waspada")

    cu, au = hist.get("copper"), hist.get("gold")
    if cu and au:
        m = dict(zip(cu["d"], cu["v"]))
        n = dict(zip(au["d"], au["v"]))
        common = sorted(set(m) & set(n))
        if len(common) > 21:
            r = [m[d] / n[d] for d in common]
            ch = (r[-1] / r[-22] - 1) * 100
            st = "tekanan" if ch < -4 else "dukung" if ch > 4 else "netral"
            add("growth", "Pertumbuhan vs defensif", st, f"Rasio tembaga/emas 20 hari {ch:+.1f}%",
                "Turun lebih dari 4% dalam 20 hari (defensif unggul) tekanan, naik lebih dari 4% mendukung")

    p = pct("brent", 5)
    if p is not None:
        st = "tekanan" if p > 6 else "dukung" if p < -6 else "netral"
        add("oil", "Minyak", st, f"Brent {vals('brent')[-1]:.1f}, 5 hari {p:+.1f}%",
            "Naik lebih dari 6% dalam 5 hari tekanan (risiko inflasi), turun lebih dari 6% mendukung")

    s = vals("spx")
    if s and len(s) > 50:
        ma = sum(s[-50:]) / 50
        gap = (s[-1] / ma - 1) * 100
        st = "dukung" if gap > 2 else "waspada" if gap < -2 else "netral"
        add("trend", "Tren S&P 500", st, f"{gap:+.1f}% dari rata-rata 50 hari",
            "Di atas rata-rata 50 hari lebih dari 2% mendukung, di bawah 2% waspada")

    p = pct("usdidr", 5)
    if p is not None:
        st = "tekanan" if p > 1 else "dukung" if p < -1 else "netral"
        idr = f"{vals('usdidr')[-1]:,.0f}".replace(",", ".")
        add("idr", "Rupiah", st, f"USD/IDR {idr}, 5 hari {p:+.2f}%",
            "USD/IDR naik lebih dari 1% dalam 5 hari (rupiah melemah) tekanan, turun lebih dari 1% mendukung")

    p = pct("eido", 1)
    if p is not None:
        st = "tekanan" if p < -1.5 else "dukung" if p > 1.5 else "netral"
        add("eido", "Petunjuk IHSG (EIDO)", st, f"EIDO sesi AS terakhir {p:+.2f}%",
            "EIDO diperdagangkan di AS setelah IHSG tutup. Turun lebih dari 1,5% tekanan, naik lebih dari 1,5% mendukung")

    pts = {"dukung": -1, "netral": 0, "waspada": 1, "tekanan": 2}
    n = len(out)
    score = sum(pts[x["state"]] for x in out)
    ratio = score / (2 * n) if n else 0
    if ratio >= 0.5:
        head = ("tekanan", "Tekanan tinggi")
    elif ratio >= 0.25:
        head = ("waspada", "Waspada")
    elif ratio >= 0:
        head = ("netral", "Campuran")
    else:
        head = ("dukung", "Mendukung aset berisiko")
    summary = {
        "state": head[0], "label": head[1], "score": score, "n": n,
        "rule": "Tekanan = 2 poin, waspada = 1, netral = 0, mendukung = -1; total dibagi 2 kali jumlah sinyal. "
                "0,5 ke atas tekanan tinggi, 0,25 ke atas waspada, 0 ke atas campuran, di bawah 0 mendukung.",
    }
    return out, summary


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="data sintetis untuk uji tampilan")
    args = ap.parse_args()

    series, errors = {}, []
    for aid, name, group, src, sym, kind in ASSETS:
        try:
            if args.demo:
                series[aid] = demo_series(aid)
            elif src == "yf":
                series[aid] = fetch_yf(sym)
            else:
                series[aid] = fetch_fred(sym)
            if aid in ("us10y", "us5y") and series[aid][-1][1] > 20:  # jaga-jaga format lama x10
                series[aid] = [(d, v / 10) for d, v in series[aid]]
            print(f"ok   {aid:8s} {sym}")
        except Exception as e:  # noqa: BLE001
            errors.append({"id": aid, "simbol": sym, "pesan": str(e)[:200]})
            print(f"GAGAL {aid:8s} {sym}: {e}", file=sys.stderr)

    if len(errors) > len(ASSETS) * 0.4:
        print("Terlalu banyak instrumen gagal, data lama tidak ditimpa.", file=sys.stderr)
        sys.exit(1)

    hist = {a: {"d": [x[0] for x in s[-300:]], "v": [round(x[1], 4) for x in s[-300:]]} for a, s in series.items()}
    assets_out = []
    for aid, name, group, src, sym, kind in ASSETS:
        if aid in series:
            assets_out.append({"id": aid, "name": name, "group": group, "symbol": sym,
                               "source": src, "kind": kind, "dp": DP.get(aid, 2),
                               **metrics(series[aid], kind)})
    signals, summary = build_signals(hist)
    now = datetime.now(timezone.utc)
    latest = {
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_wib": now.astimezone(WIB).strftime("%d %b %Y %H:%M WIB"),
        "demo": bool(args.demo),
        "assets": assets_out,
        "signals": signals,
        "summary": summary,
        "errors": errors,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "history.json").write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")
    print(f"Selesai: {len(assets_out)} instrumen, {len(errors)} gagal.")


if __name__ == "__main__":
    main()
