"""
market_context.py v5.2
日経先物・ドル円・NY市場の前日結果を取得して
今日の市場環境を判定する

v5.2変更点:
  - datetime.now() → datetime.now(JST) に統一（UTC日付ズレ修正）
  - yfinance取得失敗時のエラー内容をprint出力（GitHub Actionsログで確認可能）
"""

import yfinance as yf
import requests
from datetime import datetime, timezone, timedelta
import os

# ============================================================
# タイムゾーン定数
# ============================================================
JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    """GitHub ActionsサーバーがUTCで動いていてもJSTを返す"""
    return datetime.now(JST)


# ============================================================
# 日本株への影響度マッピング
# ============================================================
HIGH_IMPACT_KEYWORDS = [
    "nonfarm", "fed ", "fomc", "federal reserve",
    "interest rate", "cpi", "gdp",
    "boj", "bank of japan", "japan interest",
]

MEDIUM_IMPACT_KEYWORDS = [
    "retail sales", "pce", "ism", "pmi",
    "unemployment", "jolts",
    "japan cpi", "japan gdp", "tankan", "ecb",
]


def classify_event_impact(event_name: str) -> str:
    name_lower = event_name.lower()
    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in name_lower:
            return "HIGH"
    for kw in MEDIUM_IMPACT_KEYWORDS:
        if kw in name_lower:
            return "MEDIUM"
    return "LOW"


def get_market_context() -> dict:
    context = {}
    score = 0

    jst_now = now_jst()
    print(f"JST現在時刻: {jst_now.strftime('%Y-%m-%d %H:%M')} JST")

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
            print(f"日経225: {last_close:,.0f} ({change_pct:+.2f}%)")
        else:
            print(f"日経225: データ不足（{len(hist)}行）")
            context["nikkei"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"日経225 取得エラー: {type(e).__name__}: {e}")
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
            print(f"ドル円: {last:.2f} ({change_pct:+.2f}%)")
        else:
            print(f"ドル円: データ不足（{len(hist)}行）")
            context["usdjpy"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"ドル円 取得エラー: {type(e).__name__}: {e}")
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
            print(f"S&P500: {last:,.0f} ({change_pct:+.2f}%)")
        else:
            print(f"S&P500: データ不足（{len(hist)}行）")
            context["sp500"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"S&P500 取得エラー: {type(e).__name__}: {e}")
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
            print(f"Nasdaq: {last:,.0f} ({change_pct:+.2f}%)")
        else:
            print(f"Nasdaq: データ不足（{len(hist)}行）")
            context["nasdaq"] = {"price": 0, "change_pct": 0}
    except Exception as e:
        print(f"Nasdaq 取得エラー: {type(e).__name__}: {e}")
        context["nasdaq"] = {"price": 0, "change_pct": 0}

    # ⑤ 経済カレンダー
    event_impact, event_summary = _check_major_events(jst_now)
    context["has_major_event"] = event_impact in ("HIGH", "MEDIUM")
    context["event_impact"]    = event_impact
    context["event_summary"]   = event_summary

    # ⑥ 市場バイアス判定
    context["market_score"] = score
    if score >= 30:
        context["market_bias"] = "強気"
    elif score >= 20:
        context["market_bias"] = "中立"
    else:
        context["market_bias"] = "弱気"

    print(f"市場スコア: {score}/40 → {context['market_bias']}")
    return context


def _check_major_events(jst_now: datetime) -> tuple[str, str]:
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return "NONE", ""

    try:
        # JSTの日付を使う（UTC日付ズレ修正）
        today  = jst_now.strftime("%Y-%m-%d")
        print(f"Finnhub検索日付: {today}（JST）")
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
            print("重要経済指標: なし（日本株影響なし）")
            return "NONE", ""

        overall = "HIGH" if any(i == "HIGH" for i, _, _ in matched) else "MEDIUM"
        print(f"重要経済指標: {overall} ({len(matched)}件)")
        summary = _build_event_summary(overall, matched)
        return overall, summary

    except Exception as e:
        print(f"Finnhub エラー: {type(e).__name__}: {e}")
        return "NONE", ""


def _build_event_summary(overall: str, events: list) -> str:
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
