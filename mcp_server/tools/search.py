from services import search_service

def register(mcp):
    @mcp.tool()
    def search_data(keyword: str, start_date: str, end_date: str,
                     site: str = None, limit: int = 20, offset: int = 0) -> dict:
        """
        키워드와 기간으로 영화 리뷰를 검색합니다.
        - keyword: 검색할 단어 (리뷰 본문에서 부분 일치)
        - start_date, end_date: YYYY-MM-DD 형식
        - site: megabox, naver, kinolights 중 선택 (생략 시 전체)
        - limit: 최대 20~100건 (기본 20)
        - offset: pagination용 시작 위치
        """
        return search_service.search_reviews(keyword, start_date, end_date, site, limit, offset)