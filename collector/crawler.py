import os
import requests
import pymysql
from datetime import datetime

# .env 파일 직접 읽기 (간단하게)
def load_env(path=".env"):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key] = value
    return env

env = load_env()

MARKETS = "KRW-BTC,KRW-ETH,KRW-XRP,KRW-SOL,KRW-DOGE"
UPBIT_URL = f"https://api.upbit.com/v1/ticker?markets={MARKETS}"

def fetch_prices():
    response = requests.get(UPBIT_URL, timeout=10)
    response.raise_for_status()
    return response.json()

def save_to_db(data):
    conn = pymysql.connect(
        host=env["DB_HOST"],
        port=int(env["DB_PORT"]),
        user=env["DB_USER"],
        password=env["DB_PASSWORD"],
        database=env["DB_NAME"],
        charset="utf8mb4"
    )
    try:
        with conn.cursor() as cursor:
            collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in data:
                sql = """
                    INSERT INTO coin_prices
                    (market, trade_price, change_status, change_rate,
                     high_price, low_price, trade_volume_24h, collected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    item["market"],
                    item["trade_price"],
                    item["change"],
                    item["signed_change_rate"],
                    item["high_price"],
                    item["low_price"],
                    item["acc_trade_volume_24h"],
                    collected_at
                ))
        conn.commit()
        print(f"[{collected_at}] {len(data)}건 저장 완료")
    finally:
        conn.close()

if __name__ == "__main__":
    prices = fetch_prices()
    save_to_db(prices)
