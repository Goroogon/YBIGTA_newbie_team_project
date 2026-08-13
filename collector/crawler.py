import os
import pymysql
import pandas as pd
from datetime import datetime

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

CSV_PATH = "preprocessed_reviews_megabox.csv"
SITE_NAME = "megabox"
BATCH_SIZE = 20  # 한 번 실행할 때마다 20개씩 INSERT
STATE_FILE = ".crawler_state"  # 마지막으로 어디까지 넣었는지 기억하는 파일

def get_last_offset():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return int(f.read().strip())
    return 0

def save_offset(offset):
    with open(STATE_FILE, "w") as f:
        f.write(str(offset))

def save_to_db(rows):
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
            for _, row in rows.iterrows():
                sql = """
                    INSERT INTO reviews
                    (site, review_date, rating, content, cleaned_review,
                     day_of_week, tf_idf_mean_score, collected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    SITE_NAME,
                    row["date"],
                    row["rating"],
                    row["content"],
                    row["cleaned_review"],
                    row["day_of_week"],
                    row["tf_idf_mean_score"],
                    collected_at
                ))
        conn.commit()
        print(f"[{collected_at}] {len(rows)}건 저장 완료")
    finally:
        conn.close()

if __name__ == "__main__":
    df = pd.read_csv(CSV_PATH)
    total = len(df)
    offset = get_last_offset()

    if offset >= total:
        print(f"모든 데이터({total}건) 삽입 완료. 처음부터 다시 순환합니다.")
        offset = 0

    batch = df.iloc[offset:offset + BATCH_SIZE]
    if len(batch) > 0:
        save_to_db(batch)
        save_offset(offset + len(batch))
    else:
        print("삽입할 데이터가 없습니다.")
