# mcp_server/init_db.py
from database.mysql_connection import engine, Base, SessionLocal
from models.review import Review
from datetime import date, datetime
import sys

# 테이블 생성 (이건 항상 실행 — RDS든 로컬이든 필요)
Base.metadata.create_all(engine)
print("테이블 생성 완료")

# 더미 데이터는 --with-dummy 옵션 줄 때만 삽입 (로컬 테스트 전용)
if "--with-dummy" in sys.argv:
    session = SessionLocal()
    try:
        dummy = [
            Review(site="megabox", review_date=date(2026, 8, 1), rating=4.5,
                   content="정말 재밌었어요", cleaned_review="재밌 영화",
                   day_of_week="Saturday", tf_idf_mean_score=0.12,
                   collected_at=datetime.now()),
            Review(site="megabox", review_date=date(2026, 8, 5), rating=3.0,
                   content="그냥 그랬어요", cleaned_review="그냥 그랬",
                   day_of_week="Wednesday", tf_idf_mean_score=0.08,
                   collected_at=datetime.now()),
            Review(site="megabox", review_date=date(2026, 8, 10), rating=5.0,
                   content="최고의 영화입니다", cleaned_review="최고 영화",
                   day_of_week="Monday", tf_idf_mean_score=0.15,
                   collected_at=datetime.now()),
        ]
        session.add_all(dummy)
        session.commit()
        print("더미 데이터 3개 삽입 완료")
    finally:
        session.close()