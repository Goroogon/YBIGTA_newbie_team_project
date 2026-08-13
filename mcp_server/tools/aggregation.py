from services import analysis_service

def register(mcp):
    @mcp.tool()
    def aggregate_data(site: str, start_date: str, end_date: str) -> dict:
        """
        특정 사이트, 특정 기간의 리뷰 평균 평점과 리뷰 수를 집계합니다.
        - site: megabox, naver, kinolights 중 하나 (필수)
        - start_date, end_date: YYYY-MM-DD 형식
        """
        return analysis_service.aggregate_reviews(site, start_date, end_date)