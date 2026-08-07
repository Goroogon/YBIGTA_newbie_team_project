import pandas as pd
from fastapi import APIRouter

from database.mongodb_connection import mongo_db
from review_analysis.preprocessing.site_processor import SiteProcessor

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/preprocess/{site_name}")
def preprocess_reviews(site_name: str):
    raw_collection = mongo_db[f"{site_name}_raw"]
    raw_docs = list(raw_collection.find({}, {"_id": 0}))

    if not raw_docs:
        return {"status": "fail", "message": f"No raw data for '{site_name}'"}

    df = pd.DataFrame(raw_docs)
    processor = SiteProcessor(df=df, site_name=site_name)
    processor.preprocess()
    processor.feature_engineering()
    processed_records = processor.to_records()

    processed_collection = mongo_db[f"{site_name}_processed"]
    processed_collection.delete_many({})
    if processed_records:
        processed_collection.insert_many(processed_records)

    return {
        "status": "success",
        "site_name": site_name,
        "processed_count": len(processed_records),
    }