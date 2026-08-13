import re
from repositories import review_repository

MAX_KEYWORD_LENGTH = 100
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def search_reviews(keyword: str, start_date: str, end_date: str,
                    site: str = None, limit: int = 20, offset: int = 0):
    # 입력 validation
    if not keyword or len(keyword) > MAX_KEYWORD_LENGTH:
        raise ValueError("keyword는 1~100자 사이여야 합니다.")
    if not DATE_PATTERN.match(start_date) or not DATE_PATTERN.match(end_date):
        raise ValueError("날짜 형식은 YYYY-MM-DD 여야 합니다.")
    if start_date > end_date:
        raise ValueError("start_date는 end_date보다 이전이어야 합니다.")
    if site and site not in review_repository.ALLOWED_SITES:
        raise ValueError(f"허용되지 않는 site입니다. 가능한 값: {review_repository.ALLOWED_SITES}")
    if limit <= 0 or limit > 100:
        raise ValueError("limit은 1~100 사이여야 합니다.")

    results = review_repository.find_by_keyword(keyword, start_date, end_date, site, limit, offset)
    return {
        "count": len(results),
        "results": results,
    }