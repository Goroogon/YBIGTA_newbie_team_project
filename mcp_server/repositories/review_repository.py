from sqlalchemy import select, func, and_
from database.mysql_connection import SessionLocal
from models.review import Review

MAX_ROWS = 100  # 최대 조회 row 제한

ALLOWED_SITES = {"megabox", "naver", "kinolights"}  # 허용 가능한 site 값 제한


def find_by_keyword(keyword: str, start_date: str, end_date: str,
                     site: str = None, limit: int = 20, offset: int = 0):
    """키워드 + 기간으로 리뷰 검색 (pagination 지원)"""
    limit = min(limit, MAX_ROWS)

    session = SessionLocal()
    try:
        query = select(Review).where(
            and_(
                Review.content.like(f"%{keyword}%"),   # ORM이 parameterized query로 변환
                Review.review_date >= start_date,
                Review.review_date <= end_date,
            )
        )
        if site:
            query = query.where(Review.site == site)

        query = query.order_by(Review.review_date.desc()).limit(limit).offset(offset)

        result = session.execute(query).scalars().all()
        return [_to_dict(row) for row in result]
    finally:
        session.close()


def get_latest(site: str = None, limit: int = 10):
    """가장 최근에 수집된 리뷰 조회"""
    limit = min(limit, MAX_ROWS)

    session = SessionLocal()
    try:
        query = select(Review)
        if site:
            query = query.where(Review.site == site)
        query = query.order_by(Review.collected_at.desc()).limit(limit)

        result = session.execute(query).scalars().all()
        return [_to_dict(row) for row in result]
    finally:
        session.close()


def aggregate_by_period(site: str, start_date: str, end_date: str):
    """기간별 평균 평점 / 리뷰 수 집계"""
    session = SessionLocal()
    try:
        query = select(
            func.avg(Review.rating).label("avg_rating"),
            func.count(Review.id).label("review_count"),
        ).where(
            and_(
                Review.site == site,
                Review.review_date >= start_date,
                Review.review_date <= end_date,
            )
        )
        row = session.execute(query).one()
        return {
            "avg_rating": float(row.avg_rating) if row.avg_rating is not None else None,
            "review_count": row.review_count,
        }
    finally:
        session.close()


def get_available_sites():
    """현재 DB에 존재하는 site 목록 조회"""
    session = SessionLocal()
    try:
        query = select(Review.site).distinct()
        result = session.execute(query).scalars().all()
        return list(result)
    finally:
        session.close()


def _to_dict(row: Review) -> dict:
    return {
        "id": row.id,
        "site": row.site,
        "review_date": row.review_date.isoformat() if row.review_date else None,
        "rating": row.rating,
        "content": row.content,
        "cleaned_review": row.cleaned_review,
        "day_of_week": row.day_of_week,
        "tf_idf_mean_score": row.tf_idf_mean_score,
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
    }