from services import analysis_service

def register(mcp):
    @mcp.tool()
    def get_latest_data(site: str = None, limit: int = 10) -> dict:
        """
        가장 최근에 수집된 리뷰 데이터를 조회합니다.
        - site: megabox, naver, kinolights 중 선택 (생략 시 전체)
        - limit: 최대 10~100건 (기본 10)
        """
        return analysis_service.get_latest_reviews(site, limit)

    @mcp.tool()
    def get_available_sites() -> dict:
        """현재 DB에 수집되어 있는 사이트 목록을 조회합니다."""
        return analysis_service.list_available_sites()