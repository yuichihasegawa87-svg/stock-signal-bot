"""
market_context.py v5.1
日経先物・ドル円・NY市場の前日結果を取得して
今日の市場環境を判定する

v5.1変更点:
  - 重要経済指標の「日本株への影響度」を HIGH / MEDIUM / LOW の3段階で分類
  - 影響度に応じた通知文を生成（固定文言の廃止）
"""

import yfinance as yf
import requests
from datetime import datetime
import os


# ============================================================
# 日本株への影響度マッピング
# ============================================================
#
# HIGH   : 日本株が当日中に大きく動く可能性が高い指標
#          → 見送り推奨（弱気相場と重なった場合）
# MEDIUM : 影響はあるが限定的。方向感を変えるには至らないことが多い
#          → 注意喚起のみ
# LOW    : 日本株への直接影響はほぼなし
#          → 通知なし（無視）
#
# キーワードはFinnhubが返すevent名に含まれる英単語で判定

HIGH_IMPACT_KEYWORDS = [
    # 米国：最重要
    "nonfarm",          # 米雇用統計（NFP）← 最大の相場変動要因
    "fed ",             # FOMC関連
    "fomc",
    "federal reserve",
    "interest rate",    # 政策金利決定
    "cpi",              # 米CPI（インフレ指標）
    "gdp",              # 米GDP
    # 日本：最重要
    "boj",              # 日銀会合
    "bank of japan",
    "japan interest",
]

MEDIUM_IMPACT_KEYWORDS = [
    # 米国：中程度
    "retail sales",     # 米小売売上高
    "pce",              # 個人消費支出
    "ism",              # ISM製造業・非製造業
    "pmi",              # 購買担当者景気指数
    "unemployment",     # 失業率
    "jolts",            # 求人件数
    # 日本
    "japan cpi",        # 日本CPI
    "japan gdp",
    "tankan",           # 日銀短観
    # 欧州：ドル円経由で間接影響
    "ecb",              # ECB理事会
]

# それ以外（カナダCPI・英国指標等）は LOW として通知しない


def classify_event_impact(event_name: str) -> str:
    """
    イベント名から日本株への影響度を返す
    戻り値: "HIGH" / "MEDIUM" / "LOW"
    """
    name_lower = event_name.lower()
    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in name_lower:
            return "HIGH"
    for kw in MEDIUM_IMPACT_KEYWORDS:
        if kw in name_lower:
            return "MEDIUM"
    return "LOW"


def get_market_context() -> dict:
    """
    市場全体の状況を取得して辞書で返す

    戻り値例:
    {
        "nikkei":          {"price": 38250, "change_pct": 0.8},
        "usdjpy":          {"price": 153.2, "change_pct": 0.3},
        "sp500":           {"price": 5200,  "change_pct": 0.5},
        "nasdaq":          {"price": 18000, "change_pct": 0.7},
        "market_score":    35,
        "market_bias":     "強気",
        "has_major_event": True,
        "event_impact":    "HIGH",        # "HIGH"/"MEDIUM"/"LOW"/"NONE"
        "event_summary":   "🔴 日本株への影響：大きい\n..."
    }
    """
    context = {}
    score = 0

    # ① 日経225
    try:
        nk   = yf.Ticker("^N225")
        hist = nk.history(period="5d")
        if len(hist) >= 2:
            prev_close = hist["Close"].iloc[-2]
            last_close = hist["Close"].iloc[-1]
            change_pct = (last_close - prev_close) / prev_close * 100
            context["nikkei"] = {
                "price":      round(last_close, 0),
                "change_pct": round(change_pct, 2)
            }
            if change_pct > 0:
                score += 10
        else:
            context["nikkei"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"日経取得エラー: {e}")
        context["nikkei"] = {"price": 0, "change_pct": 0}

    # ② ドル円
    try:
        usdjpy = yf.Ticker("JPY=X")
        hist   = usdjpy.history(period="5d")
        if len(hist) >= 2:
            prev = hist["Close"].iloc[-2]
            last = hist["Close"].iloc[-1]
            change_pct = (last - prev) / prev * 100
            context["usdjpy"] = {
                "price":      round(last, 2),
                "change_pct": round(change_pct, 2)
            }
            if change_pct > 0:
                score += 10
        else:
            context["usdjpy"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"ドル円取得エラー: {e}")
        context["usdjpy"] = {"price": 0, "change_pct": 0}

    # ③ S&P500
    try:
        sp   = yf.Ticker("^GSPC")
        hist = sp.history(period="5d")
        if len(hist) >= 2:
            prev = hist["Close"].iloc[-2]
            last = hist["Close"].iloc[-1]
            change_pct = (last - prev) / prev * 100
            context["sp500"] = {
                "price":      round(last, 0),
                "change_pct": round(change_pct, 2)
            }
            if change_pct > 0:
                score += 10
        else:
            context["sp500"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"SP500取得エラー: {e}")
        context["sp500"] = {"price": 0, "change_pct": 0}

    # ④ ナスダック
    try:
        nq   = yf.Ticker("^IXIC")
        hist = nq.history(period="5d")
        if len(hist) >= 2:
            prev = hist["Close"].iloc[-2]
            last = hist["Close"].iloc[-1]
            change_pct = (last - prev) / prev * 100
            context["nasdaq"] = {
                "price":      round(last, 0),
                "change_pct": round(change_pct, 2)
            }
            if change_pct > 0:
                score += 10
        else:
            context["nasdaq"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"Nasdaq取得エラー: {e}")
        context["nasdaq"] = {"price": 0, "change_pct": 0}

    # ⑤ 経済カレンダー（影響度分類つき）
    event_impact, event_summary = _check_major_events()
    context["has_major_event"] = event_impact in ("HIGH", "MEDIUM")
    context["event_impact"]    = event_impact   # "HIGH"/"MEDIUM"/"NONE"
    context["event_summary"]   = event_summary  # Discord通知用テキスト

    # ⑥ 市場バイアス判定
    context["market_score"] = score
    if score >= 30:
        context["market_bias"] = "強気"
    elif score >= 20:
        context["market_bias"] = "中立"
    else:
        context["market_bias"] = "弱気"

    return context


def _check_major_events() -> tuple[str, str]:
    """
    Finnhubで本日の重要経済指標を確認し、
    日本株への影響度と通知用サマリーテキストを返す

    戻り値: (影響度, サマリーテキスト)
      影響度: "HIGH" / "MEDIUM" / "NONE"
    """
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return "NONE", ""

    try:
        today  = datetime.now().strftime("%Y-%m-%d")
        url    = "https://finnhub.io/api/v1/calendar/economic"
        params = {"from": today, "to": today, "token": api_key}
        res    = requests.get(url, params=params, timeout=10)
        data   = res.json()

        matched = []
        for e in data.get("economicCalendar", []):
            if e.get("impact") != "high":
                continue
            name   = e.get("event", "")
            impact = classify_event_impact(name)
            if impact in ("HIGH", "MEDIUM"):
                matched.append((impact, name, e.get("country", "")))

        if not matched:
            return "NONE", ""

        # 最高影響度を全体の影響度とする
        overall = "HIGH" if any(i == "HIGH" for i, _, _ in matched) else "MEDIUM"
        summary = _build_event_summary(overall, matched)
        return overall, summary

    except Exception as e:
        print(f"Finnhubエラー: {e}")
        return "NONE", ""


def _build_event_summary(overall: str, events: list) -> str:
    """
    影響度と検知したイベントリストから通知用テキストを生成する
    events: [(影響度, イベント名, 国コード), ...]
    """
    IMPACT_LABEL = {
        "HIGH":   "🔴 日本株への影響：**大きい**",
        "MEDIUM": "🟡 日本株への影響：**中程度**",
    }
    IMPACT_DESC = {
        "HIGH": (
            "発表直後にドル円・日経先物が大きく動く傾向があります。\n"
            "発表時刻をまたぐポジションは損切りラインを容易に超えるリスクがあります。"
        ),
        "MEDIUM": (
            "日本株への直接影響は限定的ですが、方向感に影響する可能性があります。\n"
            "発表後の値動きを確認してからエントリーを判断することを推奨します。"
        ),
    }

    lines = [IMPACT_LABEL[overall], ""]

    # HIGH → MEDIUM の順で列挙
    for impact in ("HIGH", "MEDIUM"):
        for ev_impact, name, country in events:
            if ev_impact != impact:
                continue
            flag = "🇺🇸" if country == "US" else ("🇯🇵" if country == "JP" else "🌐")
            tag  = "【要注意】" if impact == "HIGH" else "【注意】"
            lines.append(f"{flag} {tag} {name}")

    lines.append("")
    lines.append(IMPACT_DESC[overall])
    return "\n".join(lines)
