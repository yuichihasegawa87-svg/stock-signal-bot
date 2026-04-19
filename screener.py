"""
screener.py
J-Quants API V2 を使って前日の出来高急増・ギャップアップ銘柄を抽出する

【重要】
2025年12月22日以降に登録したユーザーはV2 APIのみ利用可能。
V2ではAPIキー1つで認証できる。メール・パスワード・トークン更新は不要。
Secretsには JQUANTS_API_KEY を登録すること。
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import time


# ============================================================
# J-Quants V2 認証
# ============================================================

def get_jquants_access_token() -> str:
    """
    V2ではAPIキーが認証情報のすべて。
    main.pyからの呼び出しインターフェースを維持するためAPIキーをそのまま返す。
    """
    api_key = os.environ.get("JQUANTS_API_KEY", "")
    if not api_key:
        raise ValueError(
            "JQUANTS_API_KEY が設定されていません。\n"
            "J-Quantsのダッシュボードでキーを発行し、"
            "GitHubのSecretsに JQUANTS_API_KEY として登録してください。"
        )
    return api_key


def _headers(token: str) -> dict:
    """V2認証ヘッダーを返す"""
    return {"x-api-key": token}


# ============================================================
# 銘柄リスト取得（V2）
# ============================================================

def get_listed_stocks(token: str) -> pd.DataFrame:
    """東証プライム・スタンダード上場銘柄の一覧を取得（V2）"""
    url = "https://api.jquants.com/v2/listed/info"
    res = requests.get(url, headers=_headers(token), timeout=15)
    res.raise_for_status()

    data    = res.json()
    records = data.get("info", data.get("data", []))
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # V2の列名に対応（スネークケースとパスカルケース両対応）
    rename = {}
    for snake, pascal in [
        ("code", "Code"),
        ("company_name", "CompanyName"),
        ("market_code_name", "MarketCodeName"),
        ("sector17_code_name", "Sector17CodeName"),
    ]:
        if snake in df.columns:
            rename[snake] = pascal
    df = df.rename(columns=rename)

    # 必要列が揃っていない場合は空を返す
    for col in ["Code", "CompanyName"]:
        if col not in df.columns:
            return pd.DataFrame()

    # プライム・スタンダード市場に絞る
    if "MarketCodeName" in df.columns:
        df = df[df["MarketCodeName"].str.contains(
            "プライム|スタンダード|Prime|Standard", na=False
        )]

    cols = [c for c in ["Code", "CompanyName", "MarketCodeName", "Sector17CodeName"]
            if c in df.columns]
    return df[cols].copy()


# ============================================================
# 株価・出来高データ取得（V2）
# ============================================================

def get_daily_quotes(token: str, code: str, days: int = 40) -> pd.DataFrame:
    """指定銘柄の日足データを取得（V2）"""
    to_date   = datetime.now().strftime("%Y%m%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    url    = "https://api.jquants.com/v2/equities/prices/daily"
    params = {"code": code, "dateFrom": from_date, "dateTo": to_date}

    res = requests.get(url, headers=_headers(token), params=params, timeout=15)
    if res.status_code != 200:
        return pd.DataFrame()

    data    = res.json()
    records = data.get("prices", data.get("data", data.get("daily_quotes", [])))
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # 日付列の統一
    for dc in ["Date", "date"]:
        if dc in df.columns:
            df["Date"] = pd.to_datetime(df[dc])
            break

    # 価格・出来高列の統一（V2はスネークケース or 調整済み列名の場合あり）
    col_map = {}
    for orig, std in [
        ("close", "Close"), ("open", "Open"), ("volume", "Volume"),
        ("AdjustmentClose", "Close"), ("AdjustmentOpen", "Open"), ("AdjustmentVolume", "Volume"),
        ("adjustment_close", "Close"), ("adjustment_open", "Open"), ("adjustment_volume", "Volume"),
    ]:
        if orig in df.columns and std not in df.columns:
            col_map[orig] = std
    df = df.rename(columns=col_map)

    if "Date" not in df.columns:
        return pd.DataFrame()

    df = df.sort_values("Date").reset_index(drop=True)
    return df


# ============================================================
# スクリーニング本体
# ============================================================

def screen_candidates(token: str, top_n: int = 20) -> pd.DataFrame:
    """
    出来高急増 + ギャップアップ候補銘柄を抽出してスコア付きで返す

    スクリーニング条件:
    1. 前日出来高が20日平均の1.5倍以上
    2. 前日終値が前々日終値より +0.5% 以上
    3. 前日の値動きが陽線（始値 < 終値）
    """
    print("銘柄リストを取得中...")
    stocks_df = get_listed_stocks(token)
    if stocks_df.empty:
        print("銘柄リストの取得に失敗しました")
        return pd.DataFrame()

    codes = stocks_df["Code"].tolist()
    print(f"取得銘柄数: {len(codes)}件 / スクリーニング開始")

    results   = []
    processed = 0

    for code in codes:
        try:
            df = get_daily_quotes(token, code, days=40)
            if df.empty or len(df) < 22:
                continue
            if not all(c in df.columns for c in ["Close", "Open", "Volume"]):
                continue

            latest = df.iloc[-1]
            prev   = df.iloc[-2]

            avg_volume = df["Volume"].iloc[-21:-1].mean()
            if avg_volume == 0:
                continue

            latest_volume    = float(latest["Volume"])
            volume_ratio     = latest_volume / avg_volume
            price_change_pct = (float(latest["Close"]) - float(prev["Close"])) / float(prev["Close"]) * 100
            is_bullish       = float(latest["Close"]) > float(latest["Open"])

            if volume_ratio >= 1.5 and price_change_pct >= 0.5 and is_bullish:
                pre_score = (
                    min(volume_ratio, 3.0) / 3.0 * 40 +
                    min(price_change_pct, 3.0) / 3.0 * 30
                )
                company_info = stocks_df[stocks_df["Code"] == code].iloc[0]
                results.append({
                    "code":             code,
                    "name":             company_info.get("CompanyName", code),
                    "sector":           company_info.get("Sector17CodeName", ""),
                    "close":            float(latest["Close"]),
                    "prev_close":       float(prev["Close"]),
                    "open":             float(latest["Open"]),
                    "volume":           int(latest_volume),
                    "avg_volume":       int(avg_volume),
                    "volume_ratio":     round(volume_ratio, 2),
                    "price_change_pct": round(price_change_pct, 2),
                    "is_bullish":       is_bullish,
                    "pre_score":        round(pre_score, 1),
                    "_df":              df
                })

            processed += 1
            if processed % 200 == 0:
                print(f"  {processed}/{len(codes)} 件処理済み...")

            time.sleep(0.2)  # API制限対策

        except Exception:
            continue

    print(f"スクリーニング通過銘柄: {len(results)}件")
    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("pre_score", ascending=False)
    return result_df.head(top_n)
