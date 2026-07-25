import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException

from review_analysis.crawling.base_crawler import BaseCrawler  # BaseCrawler 상속

# 이 파일 위치(review_analysis/crawling/naver_crawler.py) 기준으로 프로젝트 루트를 찾아
# database/ 폴더를 지정합니다. 실행 시 현재 작업 디렉터리(cwd)가 어디든 상관없이
# 항상 같은 위치(<프로젝트 루트>/database)에 저장되도록 하기 위함입니다.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = str(_PROJECT_ROOT / "database")


class NaverCrawler(BaseCrawler):
    """네이버 통합검색 '관람평' 위젯에서 리뷰를 수집하는 크롤러 클래스.

    DOM 구조:
        ul.area_card_outer
            li.area_card._item                    -> 리뷰 1건
                data-rating-id                      -> 리뷰 고유 ID (중복 제거용)
                data-report-title                   -> 리뷰 본문
                data-report-time                    -> 작성 일시, "YYYYMMDD HH:MM" 형식
                div.lego_movie_pure_star
                    span.play_star.state_fill       -> 채워진 별 조각 (개수/2 = 0~5점 별점)

    핵심 이슈와 대응:
    - '실관람객 평점' 탭은 노출 가능한 리뷰 풀 자체가 ~300개 근처로 제한되어 있어,
      그 지점에 도달하면 위젯이 "일시적인 오류가 발생했습니다 / 일시적으로
      노출되지 않습니다" 화면을 띄우며 더 이상 로드하지 않습니다. 시크릿 모드로
      테스트해도 동일하게 재현되어 세션/속도 문제가 아니라 탭 자체의 풀 한도로
      확인되었습니다.
    - 이 한계에 부딪히면(정체 지속 또는 에러 화면 감지) '네티즌' 평점 탭으로 자동
      전환하여, 별도의 리뷰 풀에서 나머지를 이어서 수집합니다. 두 탭 사이 중복은
      data-rating-id 기준으로 계속 걸러집니다.
    - 리뷰 목록은 '더보기' 버튼 없이 스크롤로만 로드되며, 가상 스크롤(virtualized
      list) 방식이라 li 개수가 늘지 않을 수도 있어 data-rating-id 기준으로 "새
      리뷰가 있는지"를 판단합니다.

    Attributes:
        output_dir (str): 저장할 데이터베이스 디렉터리 경로 (기본값: <프로젝트 루트>/database)
        target_url (str): 크롤링 대상 네이버 통합검색 URL
        driver (webdriver.Chrome | None): Selenium 웹드라이버 인스턴스
        reviews (List[Dict[str, Union[str, float]]]): 수집된 리뷰 데이터 리스트
        request_delay (float): 새 리뷰가 수집된 라운드마다 대기하는 시간(초)
    """

    LIST_SELECTOR = "ul.area_card_outer"
    ITEM_SELECTOR = "li.area_card._item"

    def __init__(
        self,
        output_dir: Optional[str] = None,
        request_delay: float = 1.0,
        headless: bool = False,
        autosave_every: int = 20,
        target_count: int = 500,
    ) -> None:
        """NaverCrawler 인스턴스를 초기화합니다.

        Args:
            output_dir (str | None): CSV 저장 디렉터리. None이면 <프로젝트 루트>/database
                (파일 위치 기준으로 계산되어, 실행 위치와 무관하게 항상 동일한 곳에 저장됨).
            request_delay (float): 새 리뷰가 수집된 라운드마다 대기하는 시간(초).
            headless (bool): 헤드리스 모드 여부.
            autosave_every (int): 이 개수만큼 새 리뷰가 쌓일 때마다 중간 저장.
            target_count (int): 목표 수집 개수.
        """
        super().__init__(output_dir or DEFAULT_OUTPUT_DIR)
        self.target_url: str = (
            "https://search.naver.com/search.naver?where=nexearch&sm=tab_etc&mra=bkEw"
            "&pkid=68&os=35442190&qvt=0&query=%EC%99%95%EA%B3%BC%20%EC%82%AC%EB%8A%94%20"
            "%EB%82%A8%EC%9E%90%20%EA%B4%80%EB%9E%8C%ED%8F%89"
        )
        self.driver: Union[webdriver.Chrome, None] = None
        self.reviews: List[Dict[str, Union[str, float]]] = []
        self.request_delay = request_delay
        self.headless = headless
        self.autosave_every = autosave_every
        self.target_count = target_count
        self._seen_ids: Set[str] = set()  # 중복 리뷰 방지용 (data-rating-id 기준, 탭 전환 후에도 유지)
        self._last_autosave_count = 0

    def start_browser(self) -> None:
        """Selenium Chrome WebDriver를 설정하고 브라우저를 실행합니다."""
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        if self.headless:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")

        # 크롬은 화면에서 가려지거나 포커스를 잃은 창/탭의 JS 타이머 실행 빈도를
        # 줄이는 백그라운드 스로틀링 기능이 있어, 창을 보고 있지 않으면 사이트
        # 자체의 지연 로딩(lazy loading) 로직이 실제로 느려집니다. 이를 억제합니다.
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-background-timer-throttling")

        self.driver = webdriver.Chrome(options=chrome_options)
        # 스크립트/페이지 로드가 응답 없이 오래 멈추는 것을 방지 (기본값은 매우 길어
        # 문제 발생 시 120초 가까이 멈춰있다가 예외가 발생하는 원인이 됨)
        self.driver.set_script_timeout(20)
        self.driver.set_page_load_timeout(30)
        self.driver.get(self.target_url)

    def _is_driver_alive(self) -> bool:
        """브라우저 세션이 아직 살아있는지 확인합니다."""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except WebDriverException:
            return False

    def scrape_reviews(self) -> None:
        """네이버 관람평에서 target_count개 이상의 리뷰(별점, 날짜, 리뷰 내용)를 크롤링합니다.

        1) '실관람객 평점' 탭(기본)에서 정체/에러가 나타날 때까지 수집
        2) 목표에 못 미쳤다면 '네티즌 평점' 탭으로 전환해 이어서 수집
        """
        self.start_browser()
        assert self.driver is not None

        try:
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, f"{self.LIST_SELECTOR} > {self.ITEM_SELECTOR}")
                    )
                )
            except TimeoutException:
                raise RuntimeError("리뷰 목록 요소를 찾지 못했습니다. 페이지 구조가 변경되었을 수 있습니다.")

            print("[디버그] '실관람객 평점' 탭에서 수집을 시작합니다.")
            self._run_collection_phase(label="실관람객")

            if len(self.reviews) < self.target_count:
                print(f"[디버그] 현재 {len(self.reviews)}개 수집, 목표 미달. '네티즌' 탭으로 전환합니다.")
                self._switch_to_netizen_tab()
                self._run_collection_phase(label="네티즌")

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
            if self.reviews:
                self.save_to_database()

    def _run_collection_phase(self, label: str) -> None:
        """현재 활성 탭에서 target_count에 도달하거나 정체/에러가 확인될 때까지 수집합니다.

        정체(새 리뷰 없음)가 max_stagnant_rounds만큼 반복되거나, 위젯의 "일시적인
        오류" 화면이 감지되면 이 탭의 풀이 소진된 것으로 보고 phase를 종료합니다
        (호출부에서 다음 탭으로 전환 여부를 결정).
        """
        assert self.driver is not None
        stagnant_rounds = 0
        max_stagnant_rounds = 6

        while len(self.reviews) < self.target_count:
            new_found = self._collect_new_reviews()

            if len(self.reviews) >= self.target_count:
                break

            if new_found == 0:
                if self._detect_widget_error():
                    print(f"[디버그] [{label}] 위젯 에러 화면 감지됨 (이 탭의 리뷰 풀 소진으로 추정). 현재 {len(self.reviews)}개")
                    return

                stagnant_rounds += 1
                print(f"[디버그] [{label}] 새 리뷰 없음 ({stagnant_rounds}/{max_stagnant_rounds}) | 현재 수집: {len(self.reviews)}개")
                if stagnant_rounds >= max_stagnant_rounds:
                    print(f"[디버그] [{label}] 더 이상 로드할 리뷰가 없는 것으로 판단합니다. (현재: {len(self.reviews)}개)")
                    return
            else:
                stagnant_rounds = 0

            try:
                self._scroll_review_list(stagnant_rounds=stagnant_rounds)
            except Exception as e:
                print(f"[경고] 스크롤 중 오류 발생, 이번 라운드는 건너뜁니다: {e}")
                if not self._is_driver_alive():
                    print("[경고] 브라우저 세션이 끊어진 것으로 보여 수집을 종료합니다.")
                    return

    def _collect_new_reviews(self) -> int:
        """현재 화면에 로드된 리뷰 중 아직 수집하지 않은 것만 골라 self.reviews에 추가합니다.

        Returns:
            이번 라운드에 새로 추가한 리뷰 개수
        """
        assert self.driver is not None
        list_el = self._get_visible_list_element()
        if list_el is None:
            return 0
        elements = list_el.find_elements(By.CSS_SELECTOR, self.ITEM_SELECTOR)

        new_found = 0
        for element in elements:
            if len(self.reviews) >= self.target_count:
                break
            try:
                rating_id = element.get_attribute("data-rating-id") or ""
                content = self._extract_content(element)
                if not content:
                    continue

                key = rating_id or content
                if key in self._seen_ids:
                    continue
                self._seen_ids.add(key)

                rating = self._extract_rating(element)
                date_text = self._extract_date(element)

                self.reviews.append(
                    {"rating": rating, "date": date_text, "content": self._sanitize_csv_field(content)}
                )
                new_found += 1
                print(f"[{len(self.reviews)}/{self.target_count}] 수집 완료 - 별점: {rating} | 날짜: {date_text}")

                if len(self.reviews) - self._last_autosave_count >= self.autosave_every:
                    self.save_to_database()
                    self._last_autosave_count = len(self.reviews)

            except Exception as e:
                print(f"[경고] 개별 리뷰 파싱 실패: {e}")
                continue

        if new_found:
            time.sleep(self.request_delay)  # 사이트 오류 방지용 텀 (라운드당 1회)

        return new_found

    def _switch_to_netizen_tab(self) -> None:
        """페이지 맨 위로 스크롤한 뒤 '네티즌' 탭을 클릭합니다.

        처음 링크로 진입했을 때와 같은 상태(맨 위)에서 탭을 클릭하고, 그 다음은
        원래 수집 루프(_run_collection_phase)가 스크롤부터 다시 이어서 진행합니다.
        전환 성공 여부를 별도로 검증하지 않습니다 — 실패했다면 이어지는 수집에서
        새 리뷰가 하나도 안 잡히고 자연스럽게 정체 판정으로 종료되므로, 별도
        검증 로직 없이도 결과적으로 안전합니다.
        """
        assert self.driver is not None
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1.0)

        candidates = self.driver.find_elements(By.CSS_SELECTOR, "li[data-tab='netizen'] a")
        tab_link = next((el for el in candidates if el.is_displayed()), None)
        if tab_link is None:
            print("[디버그] '네티즌' 탭을 찾지 못했습니다.")
            return

        try:
            tab_link.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", tab_link)

        time.sleep(2.0)  # 탭 전환 후 목록 재렌더링 대기
        print("[디버그] '네티즌' 탭 클릭 완료, 이어서 수집을 시도합니다.")

    def _detect_widget_error(self) -> bool:
        """리뷰 위젯에 '일시적인 오류' 류의 에러 화면이 떠 있는지 감지합니다.

        이 화면이 뜨면 새로고침해도 풀리지 않고(세션/속도 문제 아님), 현재 탭의
        리뷰 풀이 소진되었다는 신호로 확인되었습니다.
        """
        assert self.driver is not None
        try:
            xpath = "//*[contains(text(), '일시적인 오류') or contains(text(), '일시적으로 노출되지')]"
            for el in self.driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    return True
        except Exception:
            pass
        return False

    def _scroll_review_list(self, stagnant_rounds: int = 0) -> None:
        """리뷰 목록 위에서 실제 마우스 휠 스크롤과 동일한 이벤트를 발생시킵니다.

        스크롤 이벤트의 원점을 리뷰 목록 요소 자체로 지정해야(`ScrollOrigin`) 반응하는
        것으로 확인되어 이 방식을 기본으로 사용합니다. 목록 요소를 못 찾으면 화면에
        보이는 마지막 리뷰 li, 그마저 없으면 단순 window 스크롤로 폴백합니다.

        라운드당 커버 거리를 늘려 필요한 라운드 수 자체를 줄이기 위해, 작은 스크롤
        (400px)을 짧은 간격으로 3회 이어서 실행합니다.

        스크롤 후에는 새 리뷰(data-rating-id 기준)가 나타날 때까지 짧은 간격으로
        폴링하며, 로드되는 즉시 다음 라운드로 넘어갑니다. 최대 대기 시간은
        `stagnant_rounds`에 따라 늘어나 최대 60초까지 기다립니다.
        """
        assert self.driver is not None

        target = self._get_visible_list_element()
        if target is None:
            items = self.driver.find_elements(
                By.CSS_SELECTOR, f"{self.LIST_SELECTOR} > {self.ITEM_SELECTOR}"
            )
            visible_items = [it for it in items if it.is_displayed()]
            if visible_items:
                target = visible_items[-1]

        known_ids = self._current_item_ids()
        # 정체가 반복될수록 대기 시간을 늘리되(배치 로딩 지연 대비), 실제 원인이
        # "탭별 리뷰 풀 소진"으로 확인된 만큼 과도하게 오래 기다리지 않도록
        # 상한을 낮췄습니다 (기존 최대 90초 -> 60초).
        timeout = min(10.0 + stagnant_rounds * 10.0, 60.0)
        poll_interval = 0.2
        scroll_step = 400
        scroll_repeats = 3

        if target is not None:
            try:
                origin = ScrollOrigin.from_element(target)
                for _ in range(scroll_repeats):
                    ActionChains(self.driver).scroll_from_origin(origin, 0, scroll_step).perform()
                self._wait_for_new_items(known_ids, timeout=timeout, poll_interval=poll_interval)
                return
            except Exception as e:
                print(f"[디버그] 요소 위 휠 스크롤 실패, window 스크롤로 대체합니다: {e}")

        for _ in range(scroll_repeats):
            self.driver.execute_script(f"window.scrollBy(0, {scroll_step});")
        self._wait_for_new_items(known_ids, timeout=timeout, poll_interval=poll_interval)

    def _get_visible_list_element(self) -> Optional[WebElement]:
        """현재 화면에 실제로 보이는(is_displayed) 리뷰 목록 요소 하나를 반환합니다.

        탭(실관람객/네티즌/평론가/MY)마다 각자의 ul.area_card_outer를 갖고 있고,
        비활성 탭의 목록은 DOM에서 제거되지 않고 숨겨지기만(display:none) 합니다.
        문서 전체를 대상으로 CSS 선택자를 쓰면 숨겨진 다른 탭의 잔재 항목까지
        섞여, 탭 전환 성공 여부를 잘못 판단하는 원인이 되므로, 모든 조회는 이
        메서드가 반환하는 "현재 보이는 리스트" 하나로 범위를 한정합니다.
        """
        assert self.driver is not None
        for candidate in self.driver.find_elements(By.CSS_SELECTOR, self.LIST_SELECTOR):
            if candidate.is_displayed():
                return candidate
        return None

    def _current_item_ids(self) -> Set[str]:
        """현재 화면에 보이는 리뷰 목록의 data-rating-id 집합을 반환합니다."""
        assert self.driver is not None
        list_el = self._get_visible_list_element()
        if list_el is None:
            return set()
        ids = set()
        for element in list_el.find_elements(By.CSS_SELECTOR, self.ITEM_SELECTOR):
            try:
                rating_id = element.get_attribute("data-rating-id")
                if rating_id:
                    ids.add(rating_id)
            except Exception:
                continue
        return ids

    def _wait_for_new_items(self, known_ids: Set[str], timeout: float, poll_interval: float) -> None:
        """`known_ids`에 없는 새 리뷰가 나타날 때까지 짧게 폴링하며 대기합니다.

        먼저 확인하고 없을 때만 자는 순서(check-then-sleep)로 동작해, 이미 로드되어
        있는 경우 불필요한 대기 없이 즉시 반환합니다.
        """
        deadline = time.time() + timeout
        while True:
            if self._current_item_ids() - known_ids:
                return
            if time.time() >= deadline:
                return
            time.sleep(poll_interval)

    def _extract_rating(self, element: WebElement) -> float:
        """별점을 추출합니다 (0~5 척도).

        div.lego_movie_pure_star 안의 채워진 별 조각(span.play_star.state_fill) 개수를
        세면 0~10 척도의 점수가 나오는데, 이를 2로 나눠 0~5 척도로 저장합니다.
        """
        filled = element.find_elements(
            By.CSS_SELECTOR, "div.lego_movie_pure_star span.play_star.state_fill"
        )
        return len(filled) / 2 if filled else 0.0

    def _extract_date(self, element: WebElement) -> str:
        """날짜를 추출합니다. data-report-time 속성("20260204 10:24")을 사용합니다."""
        raw = element.get_attribute("data-report-time")
        if raw:
            try:
                return datetime.strptime(raw.strip(), "%Y%m%d %H:%M").strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass
        return ""

    def _extract_content(self, element: WebElement) -> Optional[str]:
        """리뷰 본문을 추출합니다. data-report-title 속성을 사용합니다."""
        content = element.get_attribute("data-report-title")
        return content.strip() if content else None

    @staticmethod
    def _sanitize_csv_field(value: str) -> str:
        """CSV 수식 인젝션(CSV Injection) 방지용으로 필드 값을 이스케이프합니다.

        `=`, `+`, `-`, `@`, 탭, 캐리지리턴으로 시작하는 값은 Excel 등에서 열었을 때
        수식으로 해석될 수 있어, 앞에 작은따옴표(')를 붙여 텍스트로 강제합니다.
        """
        if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value

    def save_to_database(self) -> None:
        """수집된 리뷰 데이터를 CSV 형식으로 저장합니다."""
        os.makedirs(self.output_dir, exist_ok=True)
        file_path = os.path.join(self.output_dir, "reviews_naver.csv")
        pd.DataFrame(self.reviews).to_csv(file_path, index=False, encoding="utf-8-sig")
        print(f"성공적으로 데이터를 저장했습니다: {file_path} (총 {len(self.reviews)}개)")


if __name__ == "__main__":
    # output_dir을 지정하지 않으면 이 파일 위치 기준으로 계산된
    # <프로젝트 루트>/database 에 항상 저장됩니다 (실행 위치와 무관).
    crawler = NaverCrawler(request_delay=1.0, headless=False)
    crawler.scrape_reviews()