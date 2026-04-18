"""
screener.py
J-Quants APIを使って前日の出来高急増・ギャップアップ銘柄を抽出する
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import time


# ============================================================
# J-Quants 認証
# ============================================================

def get_jquants_access_token() -> str:
    """
    リフレッシュトークンからアクセストークンを取得
    （アクセストークンは24時間有効）
    """
    refresh_token = os.environ.get("JQUANTS_REFRESH_TOKEN", "")
    if not refresh_token:
        raise ValueError("JQUANTS_REFRESH_TOKEN が設定されていません")

    url = "https://api.jquants.com/v1/token/auth_refresh"
    params = {"refreshtoken": refresh_token}
    res = requests.post(url, params=params, timeout=15)
    res.raise_for_status()
    return res.json()["idToken"]


# ============================================================
# 銘柄リスト取得
# ============================================================

def get_listed_stocks(token: str) -> pd.DataFrame:
    """
    東証プライム・スタンダード上場銘柄の一覧を取得
    """
    url = "https://api.jquants.com/v1/listed/info"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    df = pd.DataFrame(res.json()["info"])

    # プライム市場（市場区分コード0111）とスタンダード（0121）に絞る
    df = df[df["MarketCodeName"].str.contains("プライム|スタンダード", na=False)]
    return df[["Code", "CompanyName", "MarketCodeName", "Sector17CodeName"]]


# ============================================================
# 株価・出来高データ取得
# ============================================================

def get_daily_quotes(token: str, code: str, days: int = 30) -> pd.DataFrame:
    """
    指定銘柄の日足データを取得（最大30日分）
    """
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    url = "https://api.jquants.com/v1/prices/daily_quotes"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"code": code, "from": from_date, "to": to_date}

    res = requests.get(url, headers=headers, params=params, timeout=15)
    if res.status_code != 200:
        return pd.DataFrame()

    data = res.json().get("daily_quotes", [])
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    return df


# ============================================================
# スクリーニング本体
# ============================================================

def screen_candidates(token: str, top_n: int = 20) -> pd.DataFrame:
    """
    出来高急増 + ギャップアップ候補銘柄を抽出してスコア付きで返す

    スクリーニング条件:
    1. 前日出来高が20日平均の1.5倍以上
    2. 前日終値が前々日終値より +0.5% 以上（ギャップor上昇）
    3. 前日の値動きが陽線（始値 < 終値）
    """
    print("銘柄リストを取得中...")
    stocks_df = get_listed_stocks(token)
    codes = stocks_df["Code"].tolist()

    print(f"取得銘柄数: {len(codes)}件 / スクリーニング開始")

    results = []
    processed = 0

    for code in codes:
        try:
            df = get_daily_quotes(token, code, days=30)
            if len(df) < 22:
                continue

            # 最新2日分
            latest = df.iloc[-1]
            prev   = df.iloc[-2]

            # 20日平均出来高
            avg_volume = df["Volume"].iloc[-21:-1].mean()
            if avg_volume == 0:
                continue

            latest_volume = latest["Volume"]
            volume_ratio  = latest_volume / avg_volume  # 出来高比率

            # 前日比騰落率
            price_change_pct = (latest["Close"] - prev["Close"]) / prev["Close"] * 100

            # 陽線判定
            is_bullish = latest["Close"] > latest["Open"]

            # 条件チェック
            if volume_ratio >= 1.5 and price_change_pct >= 0.5 and is_bullish:
                # スクリーニングスコア（後でscorerが詳細スコアを付与）
                pre_score = (
                    min(volume_ratio, 3.0) / 3.0 * 40 +   # 出来高比率（最大40点）
                    min(price_change_pct, 3.0) / 3.0 * 30  # 上昇率（最大30点）
                )

                # 銘柄名を結合
                company_info = stocks_df[stocks_df["Code"] == code].iloc[0]

                results.append({
                    "code": code,
                    "name": company_info["CompanyName"],
                    "sector": company_info["Sector17CodeName"],
                    "close": latest["Close"],
                    "prev_close": prev["Close"],
                    "open": latest["Open"],
                    "volume": int(latest_volume),
                    "avg_volume": int(avg_volume),
                    "volume_ratio": round(volume_ratio, 2),
                    "price_change_pct": round(price_change_pct, 2),
                    "is_bullish": is_bullish,
                    "pre_score": round(pre_score, 1),
                    # 後でscorerが使う生データ
                    "_df": df
                })

            processed += 1
            if processed % 200 == 0:
                print(f"  {processed}/{len(codes)} 件処理済み...")

            # API制限対策（1秒間に5リクエストまで）
            time.sleep(0.2)

        except Exception as e:
            continue

    print(f"スクリーニング通過銘柄: {len(results)}件")

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("pre_score", ascending=False)

    # 上位top_n件を返す（scorerで詳細分析するため）
    return result_df.head(top_n)
