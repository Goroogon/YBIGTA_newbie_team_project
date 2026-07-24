import json
import os
import random
import re
import time
from typing import Any, Dict, List, Optional
 
import pandas as pd
import requests
from bs4 import BeautifulSoup
 
from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger
 
 
SEASON_REVIEWS_QUERY = """
query SeasonReviews(
    $movieId: Int!
    $offset: Int = 0
    $limit: Int = 10
    $orderBy: ReviewMoviesOrderType! = WRITTEN_AT
    $orderOption: OrderOptionType! = DESC
) {
  reviewsCount(movieId: $movieId)
  reviews(
    movieId: $movieId
    offset: $offset
    limit: $limit
    orderBy: $orderBy
    orderOption: $orderOption
  ) {
    id
    reviewTitle
    review
    createdAt
    userStarRating {
      star
    }
  }
}
"""
 
 
class KinolightsCrawler(BaseCrawler):
    """kinolights <왕과 사는 남자> 리뷰를 크롤링하는 클래스.
 
    kinolights는 Next.js 기반 SPA로, 리뷰 페이지에 처음 접속하면
    서버가 첫 페이지 분량의 리뷰 데이터를 HTML의 <script> 태그 안에
    JSON 형태로 직접 내려준다(SSR 스트리밍). 이 초기 데이터는
    requests + BeautifulSoup으로 HTML을 받아 해당 <script> 태그를 찾고
    내부에 담긴 JSON을 파싱해서 얻는다.
 
    이후 나머지 리뷰(500개 이상 채우기 위한 분량)는 페이지 내부에서
    실제로 호출하는 것과 동일한 GraphQL API
    (https://gateway.kinolights.com/graphql)를 requests.Session으로
    직접 호출하여 offset을 늘려가며 페이지네이션 방식으로 수집한다.
    리뷰가 스크롤 시 JS로 새로 렌더링되는 구조가 아니라 API 응답을
    그대로 받아오는 구조라 Selenium 없이도 안정적으로 수집이 가능하다.
 
    별점, 작성일, 리뷰 내용을 최소 500개 이상 수집하여
    output_dir 하위에 reviews_kinolights.csv 로 저장한다.
    리뷰 내용이 비어있거나 별점이 없는 리뷰는 최소조건(별점/날짜/내용 모두 포함)을
    만족시키기 위해 수집에서 제외한다.
    """
 
    PAGE_URL = "https://m.kinolights.com/season/148606/reviews"
    GRAPHQL_URL = "https://gateway.kinolights.com/graphql"
    MOVIE_ID = 148606  # '왕과 사는 남자'
 
    def __init__(self, output_dir: str) -> None:
        super().__init__(output_dir)
        self.session: Optional[requests.Session] = None
        self.reviews_data: List[Dict[str, Any]] = []
        self.logger = setup_logger("kinolights_crawler.log")
 
    def start_browser(self) -> None:
        """실제 브라우저 대신, HTML/GraphQL 요청에 사용할 requests.Session을 준비한다.
 
        kinolights는 별도 인증 토큰 없이 origin/referer/user-agent 헤더만으로
        페이지 접속과 API 호출이 모두 가능한 것으로 확인되어, 브라우저 자동화
        없이 세션과 헤더만 세팅한다.
        """
        self.session = requests.Session()
        self.session.headers.update(
            {
                "accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/webp,*/*;q=0.8"
                ),
                "origin": "https://m.kinolights.com",
                "referer": "https://m.kinolights.com/",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/150.0.0.0 Safari/537.36"
                ),
            }
        )
        self.logger.info("requests.Session 준비 완료 (HTML/GraphQL 요청용)")
 
    def _parse_initial_reviews_from_html(self, html: str) -> Dict[str, Any]:
        """리뷰 페이지 HTML을 BeautifulSoup으로 파싱해, <script> 태그 안에
        SSR로 내려온 SeasonReviews 초기 데이터(JSON)를 추출한다.
 
        Next.js는 스트리밍 방식으로 <script> 태그 본문에 JSON을 직접 심어두므로,
        BeautifulSoup으로 모든 <script> 태그를 순회하며 리뷰 데이터가 담긴
        태그를 찾은 뒤, json.JSONDecoder로 해당 위치부터 유효한 JSON 객체만
        정확히 파싱한다. 찾지 못하면 빈 dict를 반환한다.
        """
        soup = BeautifulSoup(html, "html.parser")
        decoder = json.JSONDecoder()
 
        for script in soup.find_all("script"):
            text = script.string
            if not text or '"reviewsCount"' not in text or '"reviews"' not in text:
                continue
 
            match = re.search(r'\{"type":"next","value":\{"data":', text)
            if not match:
                continue
 
            try:
                obj, _ = decoder.raw_decode(text, match.start())
            except json.JSONDecodeError as e:
                self.logger.error(f"초기 리뷰 JSON 파싱 실패: {e}")
                continue
 
            data = obj.get("value", {}).get("data", {})
            if "reviews" in data and "reviewsCount" in data:
                return data
 
        self.logger.error("HTML에서 초기 리뷰 데이터를 찾지 못했습니다.")
        return {}
 
    def _fetch_page(self, offset: int, limit: int) -> Dict[str, Any]:
        """지정한 offset, limit으로 SeasonReviews GraphQL 쿼리를 1회 호출한다."""
        assert self.session is not None
        payload = {
            "operationName": "SeasonReviews",
            "query": SEASON_REVIEWS_QUERY,
            "variables": {
                "movieId": self.MOVIE_ID,
                "offset": offset,
                "limit": limit,
                "orderBy": "WRITTEN_AT",
                "orderOption": "DESC",
            },
        }
        headers = {
            "content-type": "application/json",
            "accept": "application/graphql-response+json,application/json;q=0.9",
        }
        response = self.session.post(
            self.GRAPHQL_URL, json=payload, headers=headers, timeout=10
        )
        response.raise_for_status()
        return response.json()
 
    def _extract_review(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """리뷰 하나에서 별점/날짜/내용을 뽑아낸다. 최소조건을 만족하지 못하면 None."""
        # kinolights는 한줄 코멘트를 reviewTitle에 담고 review(본문)는
        # 비워두는 경우가 대부분이라, review가 비어있으면 reviewTitle을
        # 리뷰 내용으로 사용한다.
        content = (item.get("review") or "").strip()
        if not content:
            content = (item.get("reviewTitle") or "").strip()
        if not content:
            return None
 
        star_rating = item.get("userStarRating")
        if not star_rating or star_rating.get("star") is None:
            return None
 
        created_at = item.get("createdAt")
        if not created_at:
            return None
 
        return {
            "rating": star_rating["star"],
            "date": created_at[:10],  # YYYY-MM-DD 부분만 사용
            "content": content,
        }
 
    def scrape_reviews(self, min_count: int = 500) -> None:
        """리뷰 페이지 HTML에서 초기 리뷰를 파싱한 뒤, 부족한 만큼 GraphQL API를
        반복 호출해 offset을 늘려가며 리뷰를 수집한다.
 
        서버가 보고하는 reviewsCount와 min_count 중 먼저 도달하는 조건에서
        수집을 종료한다. 리뷰 내용이 없거나 별점이 없는 항목은 제외한다.
        중간에 요청이 실패하면 최대 3회까지 재시도한 뒤 다음 페이지로 넘어간다.
        """
        if self.session is None:
            self.start_browser()
        assert self.session is not None
 
        max_retries = 3
        limit = 20
        total_count: Optional[int] = None
 
        # 1) BeautifulSoup으로 초기 페이지의 리뷰(첫 배치)를 파싱
        try:
            page_response = self.session.get(self.PAGE_URL, timeout=10)
            page_response.raise_for_status()
            initial_data = self._parse_initial_reviews_from_html(page_response.text)
        except requests.RequestException as e:
            self.logger.error(f"리뷰 페이지 로드 실패: {e}")
            initial_data = {}
 
        initial_items = initial_data.get("reviews", []) or []
        total_count = initial_data.get("reviewsCount")
        if total_count is not None:
            self.logger.info(f"전체 리뷰 개수: {total_count}")
 
        for item in initial_items:
            review = self._extract_review(item)
            if review:
                self.reviews_data.append(review)
 
        offset = len(initial_items)
        self.logger.info(
            f"초기 페이지 파싱 완료 - 누적 리뷰 수: {len(self.reviews_data)}"
        )
 
        # 2) 부족한 만큼 GraphQL API를 직접 호출하며 offset을 늘려 수집
        while len(self.reviews_data) < min_count:
            if total_count is not None and offset >= total_count:
                self.logger.info("서버가 보고한 전체 리뷰 수만큼 수집을 완료했습니다.")
                break
 
            data: Optional[Dict[str, Any]] = None
            for attempt in range(1, max_retries + 1):
                try:
                    data = self._fetch_page(offset, limit)
                    break
                except requests.RequestException as e:
                    self.logger.error(f"요청 실패 (offset={offset}, {attempt}회차): {e}")
                    time.sleep(random.uniform(2.0, 4.0))
 
            if data is None:
                self.logger.error(f"offset={offset} 재시도 모두 실패, 수집을 종료합니다.")
                break
 
            result = data.get("data", {})
            if total_count is None:
                total_count = result.get("reviewsCount", 0)
                self.logger.info(f"전체 리뷰 개수: {total_count}")
 
            review_items = result.get("reviews", []) or []
            if not review_items:
                self.logger.info(f"offset={offset}에 더 이상 리뷰가 없어 수집을 종료합니다.")
                break
 
            for item in review_items:
                review = self._extract_review(item)
                if review:
                    self.reviews_data.append(review)
 
            self.logger.info(
                f"offset={offset} 완료 - 누적 리뷰 수: {len(self.reviews_data)}"
            )
            offset += limit
            time.sleep(random.uniform(0.5, 1.5))
 
        self.logger.info(f"최종 파싱된 리뷰 수: {len(self.reviews_data)}")
 
    def save_to_database(self) -> None:
        """수집한 리뷰 데이터를 output_dir 하위에 reviews_kinolights.csv 로 저장한다."""
        df = pd.DataFrame(self.reviews_data)
        df = df.reset_index(drop=True)
 
        os.makedirs(self.output_dir, exist_ok=True)
        save_path = os.path.join(self.output_dir, "reviews_kinolights.csv")
        df.to_csv(save_path, index=False, encoding="utf-8-sig")
 
        self.logger.info(f"CSV 저장 완료: {save_path} (총 {len(df)}개)")