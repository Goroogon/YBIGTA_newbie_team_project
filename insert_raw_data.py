import pandas as pd
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["ybigta_db"]

# site_name : CSV 파일 경로
sites = {
    "kinolights": "database/reviews_kinolights.csv",
    "megabox": "database/reviews_megabox.csv",
    "naver": "database/reviews_naver.csv",
}

for site_name, csv_path in sites.items():
    df = pd.read_csv(csv_path)
    records = df.to_dict("records")

    collection_name = f"{site_name}_raw"
    collection = db[collection_name]

    # 재실행 시 중복 삽입 방지 (선택: 기존 데이터 삭제 후 새로 삽입)
    collection.delete_many({})

    if records:
        collection.insert_many(records)

    print(f"[{collection_name}] {len(records)}개 문서 삽입 완료")

print("전체 완료")