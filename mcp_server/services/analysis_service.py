import re
from repositories import review_repository

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_latest_reviews(site: str = None, limit: int = 10):
    if site and site not in review_repository.ALLOWED_SITES:
        raise ValueError(f"허용되지 않는 site입니다. 가능한 값: {review_repository.ALLOWED_SITES}")
    if limit <= 0 or limit > 100:
        raise ValueError("limit은 1~100 사이여야 합니다.")

    results = review_repository.get_latest(site, limit)
    return {
        "count": len(results),
        "results": results,
    }


def aggregate_reviews(site: str, start_date: str, end_date: str):
    if site not in review_repository.ALLOWED_SITES:
        raise ValueError(f"허용되지 않는 site입니다. 가능한 값: {review_repository.ALLOWED_SITES}")
    if not DATE_PATTERN.match(start_date) or not DATE_PATTERN.match(end_date):
        raise ValueError("날짜 형식은 YYYY-MM-DD 여야 합니다.")
    if start_date > end_date:
        raise ValueError("start_date는 end_date보다 이전이어야 합니다.")

    stats = review_repository.aggregate_by_period(site, start_date, end_date)
    return {
        "site": site,
        "period": {"start": start_date, "end": end_date},
        **stats,
    }


def list_available_sites():
    return {"sites": review_repository.get_available_sites()}