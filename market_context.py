"""
market_context.py
日経先物・ドル円・NY市場の前日結果を取得して
今日の市場環境を判定する
"""

import yfinance as yf
import requests
from datetime import datetime, timedelta
import os


def get_market_context() -> dict:
    """
    市場全体の状況を取得して辞書で返す
    戻り値例:
    {
        "nikkei_futures": {"price": 38250, "change_pct": 0.8},
        "usdjpy": {"price": 153.2, "change_pct": 0.3},
        "sp500": {"price": 5200, "change_pct": 0.5},
        "nasdaq": {"price": 18000, "change_pct": 0.7},
        "market_score": 35,   # 最大40点
        "market_bias": "強気" # 強気 / 弱気 / 中立
    }
    """
    context = {}
    score = 0

    # ① 日経225（period=5dで取得し直近2営業日を使う。週末・祝日対策）
    try:
        nk = yf.Ticker("^N225")
        hist = nk.history(period="5d")
        if len(hist) >= 2:
            prev_close = hist["Close"].iloc[-2]
            last_close = hist["Close"].iloc[-1]
            change_pct = (last_close - prev_close) / prev_close * 100
            context["nikkei"] = {
                "price": round(last_close, 0),
                "change_pct": round(change_pct, 2)
            }
            if change_pct > 0:
                score += 10
        else:
            context["nikkei"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"日経取得エラー: {e}")
        context["nikkei"] = {"price": 0, "change_pct": 0}

    # ② ドル円（period=5d）
    try:
        usdjpy = yf.Ticker("JPY=X")
        hist = usdjpy.history(period="5d")
        if len(hist) >= 2:
            prev = hist["Close"].iloc[-2]
            last = hist["Close"].iloc[-1]
            change_pct = (last - prev) / prev * 100
            context["usdjpy"] = {
                "price": round(last, 2),
                "change_pct": round(change_pct, 2)
            }
            # 円安（ドル高）→ 輸出株有利
            if change_pct > 0:
                score += 10
        else:
            context["usdjpy"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"ドル円取得エラー: {e}")
        context["usdjpy"] = {"price": 0, "change_pct": 0}

    # ③ S&P500（period=5d）
    try:
        sp = yf.Ticker("^GSPC")
        hist = sp.history(period="5d")
        if len(hist) >= 2:
            prev = hist["Close"].iloc[-2]
            last = hist["Close"].iloc[-1]
            change_pct = (last - prev) / prev * 100
            context["sp500"] = {
                "price": round(last, 0),
                "change_pct": round(change_pct, 2)
            }
            if change_pct > 0:
                score += 10
        else:
            context["sp500"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"SP500取得エラー: {e}")
        context["sp500"] = {"price": 0, "change_pct": 0}

    # ④ ナスダック（period=5d）
    try:
        nq = yf.Ticker("^IXIC")
        hist = nq.history(period="5d")
        if len(hist) >= 2:
            prev = hist["Close"].iloc[-2]
            last = hist["Close"].iloc[-1]
            change_pct = (last - prev) / prev * 100
            context["nasdaq"] = {
                "price": round(last, 0),
                "change_pct": round(change_pct, 2)
            }
            if change_pct > 0:
                score += 10
        else:
            context["nasdaq"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"Nasdaq取得エラー: {e}")
        context["nasdaq"] = {"price": 0, "change_pct": 0}

    # ⑤ 経済カレンダー（重要イベント確認）
    context["has_major_event"] = _check_major_events()

    # ⑥ 市場バイアス判定
    context["market_score"] = score
    if score >= 30:
        context["market_bias"] = "強気"
    elif score >= 20:
        context["market_bias"] = "中立"
    else:
        context["market_bias"] = "弱気"

    return context


def _check_major_events() -> bool:
    """
    Finnhubで本日の重要経済指標を確認
    FOMCや日銀会合など重大イベントがある日はTrueを返す
    """
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return False

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/calendar/economic"
        params = {"from": today, "to": today, "token": api_key}
        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        high_impact_events = [
            e for e in data.get("economicCalendar", [])
            if e.get("impact") == "high"
        ]
        return len(high_impact_events) > 0
    except Exception as e:
        print(f"Finnhubエラー: {e}")
        return False
