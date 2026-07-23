from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

import pandas as pd
import re
import time
import random
import datetime
import os

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger


class MegaboxCrawler(BaseCrawler):
    """메가박스 <왕과 사는 남자> 관람평을 크롤링하는 클래스.

    별점, 작성일, 리뷰 내용을 최소 500개 이상 수집하여
    output_dir 하위에 reviews_megabox.csv 로 저장한다.
    리뷰 내용이 비어있는 관람평(별점만 남긴 경우)은 수집에서 제외한다.
    """

    def __init__(self, output_dir: str):
        super().__init__(output_dir)
        self.base_url = "https://www.megabox.co.kr/movie-detail/comment?rpstMovieNo=25104500"
        self.driver = None
        self.reviews_data = []
        self.logger = setup_logger("megabox_crawler.log")

    def start_browser(self):
        """Edge 브라우저를 실행하고 <왕과 사는 남자> 관람평 페이지로 접속한다."""
        edge_options = Options()
        edge_options.add_experimental_option("detach", True)
        edge_options.add_experimental_option("excludeSwitches", ["enable-logging"])

        self.driver = webdriver.Edge(options=edge_options)
        self.driver.get(self.base_url)
        self.driver.maximize_window()
        self.driver.implicitly_wait(2)

        self.logger.info(f"브라우저 실행 및 접속 완료: {self.base_url}")

    def scrape_reviews(self, min_count: int = 500):
        """페이지 번호를 순서대로 클릭하며 리뷰를 수집한다.

        메가박스는 무한스크롤이 아니라 페이지네이션 방식이라,
        pagenum 속성을 가진 페이지 버튼을 순서대로 클릭하며 진행한다.
        리뷰 내용이 빈 경우(별점만 남긴 관람평)는 최소조건(별점/날짜/내용 모두 포함)을
        만족시키기 위해 수집에서 제외한다.
        """
        if self.driver is None:
            self.start_browser()

        page = 1
        max_page = 300  # 안전장치: 빈 리뷰 제외 감안해 여유 있게 설정

        while page <= max_page:
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            review_items = soup.select("li.type01.oneContentTag")

            if not review_items:
                self.logger.info(f"{page}페이지에 리뷰가 없어 수집을 종료합니다.")
                break

            for item in review_items:
                blank = {}

                rating_tag = item.select_one("div.story-point span")
                if rating_tag:
                    blank["rating"] = rating_tag.get_text(strip=True)
                else:
                    self.logger.error("별점 가져올때 문제발생")
                    continue

                content_tag = item.select_one("div.story-txt")
                if content_tag:
                    content_text = content_tag.get_text(strip=True)
                    content_text = content_text.replace("\n", " ").replace("\r", " ")
                    # 일반 공백류 문자뿐 아니라, 점자 없음(U+2800) 같은
                    # '보이지 않는 빈칸 위장 문자'까지 제거한 뒤 실질적으로
                    # 아무 내용도 남지 않으면 빈 리뷰로 간주하고 제외한다.
                    content_text_check = content_text.replace("\u2800", "")
                    if not re.sub(r"\s+", "", content_text_check):
                        continue
                    blank["content"] = content_text
                else:
                    self.logger.error("리뷰 내용 가져올때 문제발생")
                    continue

                date_tag = item.select_one("div.story-date span")
                if date_tag:
                    blank["date"] = self._parse_date(date_tag.get_text(strip=True))
                else:
                    self.logger.error("날짜 가져올때 문제발생")
                    continue

                self.reviews_data.append(blank)

            self.logger.info(f"{page}페이지 완료 - 누적 리뷰 수: {len(self.reviews_data)}")

            if len(self.reviews_data) >= min_count:
                self.logger.info(f"목표 리뷰 수({min_count}개) 도달, 수집을 종료합니다.")
                break

            # 다음 페이지로 이동
            next_page = page + 1
            try:
                next_button = self.driver.find_element(By.XPATH, f"//a[@pagenum='{next_page}']")
                next_button.click()
                time.sleep(random.uniform(2.0, 4.0))
                page = next_page
            except Exception as e:
                self.logger.info(f"다음 페이지({next_page})를 찾을 수 없어 수집을 종료합니다: {e}")
                break

        self.logger.info(f"최종 파싱된 리뷰 수: {len(self.reviews_data)}")
        self.driver.quit()

    def _parse_date(self, text: str) -> str:
        """'1 시간전' 같은 상대 시간, 또는 '2026.07.10' 같은 절대 날짜를 모두 처리한다."""
        text = text.strip()
        now = datetime.datetime.now()

        # 절대 날짜 형식 (2026.07.10) 먼저 확인
        absolute_match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
        if absolute_match:
            year, month, day = absolute_match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        # 상대 시간 형식 처리 ('방금', 'N분전', 'N시간전' 등)
        if "방금" in text:
            return now.strftime("%Y-%m-%d")

        relative_match = re.search(r"(\d+)\s*(분|시간|일|주|개월|년)", text)
        if relative_match:
            num = int(relative_match.group(1))
            unit = relative_match.group(2)

            if unit == "분":
                result = now - datetime.timedelta(minutes=num)
            elif unit == "시간":
                result = now - datetime.timedelta(hours=num)
            elif unit == "일":
                result = now - datetime.timedelta(days=num)
            elif unit == "주":
                result = now - datetime.timedelta(weeks=num)
            elif unit == "개월":
                result = now - datetime.timedelta(days=num * 30)
            elif unit == "년":
                result = now - datetime.timedelta(days=num * 365)
            else:
                result = now

            return result.strftime("%Y-%m-%d")

        return None

    def save_to_database(self):
        """수집한 리뷰 데이터를 output_dir 하위에 reviews_megabox.csv 로 저장한다."""
        df = pd.DataFrame(self.reviews_data)
        df = df.reset_index(drop=True)

        os.makedirs(self.output_dir, exist_ok=True)
        save_path = os.path.join(self.output_dir, "reviews_megabox.csv")
        df.to_csv(save_path, index=False, encoding="utf-8-sig")

        self.logger.info(f"CSV 저장 완료: {save_path} (총 {len(df)}개)")