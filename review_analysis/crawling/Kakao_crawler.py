import os
import re
import time
from typing import Dict, List, Union, Optional, Set, Tuple

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException,
    InvalidSessionIdException,
    WebDriverException,
)

from review_analysis.crawling.base_crawler import BaseCrawler  # BaseCrawler 상속


class KakaoCrawler(BaseCrawler):
    """카카오맵 장소 리뷰 수집을 위한 크롤러 클래스.

    BaseCrawler를 상속받아 Selenium을 활용해 리뷰 데이터를 크롤링하고 CSV로 저장합니다.

    실제 DOM 구조 (개발자도구로 확인됨, iframe 아님, top-level DOM):
        ul.list_review > li ... div.review_detail
            div.info_grade
                span.starred_grade
                    span.screen_out  -> "별점" (라벨)
                    span.screen_out  -> "5.0"  (실제 별점 값)
                    span.wrap_grade > span.figure_star.on (채워진 별)
                span.txt_date        -> "2026.07.01."
            div.wrap_review
                a.link_review        -> 리뷰 본문 텍스트

    리뷰 로딩은 '더보기' 버튼이 아니라 페이지 하단까지 스크롤하면
    추가 리뷰가 로드되는 무한 스크롤 방식입니다.

    Attributes:
        output_dir (str): 저장할 데이터베이스 디렉터리 경로
        target_url (str): 크롤링 대상 카카오맵 URL
        driver (webdriver.Chrome | None): Selenium 웹드라이버 인스턴스
        reviews (List[Dict[str, Union[str, float]]]): 수집된 리뷰 데이터 리스트
        request_delay (float): 리뷰 1건 처리 후 대기 시간(초)
    """

    LIST_SELECTOR_CANDIDATES = [
        "ul.list_review",
        "ul.list_evaluation",
        "div.evaluation_review ul",
    ]

    def __init__(
        self,
        output_dir: str,
        request_delay: float = 0.5,
        headless: bool = False,
        autosave_every: int = 20,
    ) -> None:
        """KakaoCrawler 인스턴스를 초기화합니다.

        Args:
            output_dir (str): CSV 파일이 저장될 출력 디렉터리 경로
            request_delay (float): 리뷰 1건 처리 후 대기 시간(초)
            headless (bool): 헤드리스 모드 여부
            autosave_every (int): 이 개수만큼 새 리뷰가 쌓일 때마다 중간 저장.
                브라우저가 도중에 꺼지거나(창을 실수로 닫음, 절전모드, Chrome 자동 업데이트 등)
                세션이 끊겨도 그동안 모은 데이터를 잃지 않기 위함입니다.
        """
        super().__init__(output_dir)
        self.target_url: str = "https://place.map.kakao.com/17733090#review"
        self.driver: Union[webdriver.Chrome, None] = None
        self.reviews: List[Dict[str, Union[str, float]]] = []
        self.request_delay = request_delay
        self.headless = headless
        self.autosave_every = autosave_every
        self._in_iframe = False
        self._seen_keys: Set[Tuple[str, str]] = set()  # 중복 리뷰 방지용 (날짜+본문 앞부분 기반)
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

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.get(self.target_url)
        time.sleep(3)  # 초기 페이지 로딩 대기

    def _find_review_iframe(self) -> Optional[str]:
        """혹시 리뷰 목록이 iframe 안에 있는 경우를 대비한 폴백 탐색.

        스크린샷으로 확인한 현재 페이지 구조는 top-level DOM이라 보통은
        필요 없지만, 페이지 구조가 바뀔 경우를 대비해 남겨둡니다.
        """
        assert self.driver is not None
        self.driver.switch_to.default_content()
        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        print(f"[디버그] 발견된 iframe 개수: {len(iframes)}")

        for idx, frame in enumerate(iframes):
            name = frame.get_attribute("name") or frame.get_attribute("id") or f"frame_{idx}"
            try:
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(frame)
                for sel in self.LIST_SELECTOR_CANDIDATES:
                    if self.driver.find_elements(By.CSS_SELECTOR, sel):
                        print(f"[디버그] 리뷰 목록을 iframe '{name}' 안에서 찾음 (셀렉터: {sel})")
                        return name
            except Exception:
                continue

        self.driver.switch_to.default_content()
        return None

    def _locate_review_list_selector(self, timeout: int = 10) -> Optional[str]:
        """현재 driver 컨텍스트에서 유효한 리뷰 리스트 셀렉터를 찾습니다."""
        assert self.driver is not None
        wait = WebDriverWait(self.driver, timeout)
        for sel in self.LIST_SELECTOR_CANDIDATES:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"{sel} > li")))
                return sel
            except TimeoutException:
                continue
        return None

    def scrape_reviews(self) -> None:
        """카카오맵에서 500개 이상의 리뷰(별점, 날짜, 리뷰 내용)를 크롤링합니다.

        브라우저 세션이 중간에 끊겨도(창이 실수로 닫히거나, PC가 절전모드로
        전환되거나, Chrome이 자동 업데이트로 재시작되는 등) 자동으로 브라우저를
        다시 켜고 이어서 수집합니다. self.reviews와 self._seen_keys는 인스턴스에
        유지되므로, 재시작해도 처음부터 다시 모으지 않고 이어서 채웁니다.
        """
        max_session_retries = 5  # 세션이 끊겼을 때 브라우저를 재시작할 최대 횟수

        for attempt in range(1, max_session_retries + 1):
            session_lost = self._scrape_single_session()

            if len(self.reviews) >= 500:
                return

            if not session_lost:
                # 세션은 안 끊겼는데 500개를 못 채웠다면(더 이상 로드할 리뷰가 없음)
                # 재시도해도 의미가 없으므로 종료
                return

            print(
                f"[안내] 세션이 끊겨 중단되었지만, 지금까지 모은 {len(self.reviews)}개 리뷰는 저장되었습니다. "
                f"브라우저를 재시작해서 이어서 수집합니다 (재시작 {attempt}/{max_session_retries})..."
            )

        print(
            f"[안내] 최대 재시작 횟수({max_session_retries}회)에 도달했습니다. "
            f"현재까지 모은 리뷰 수: {len(self.reviews)}개"
        )

    def _scrape_single_session(self) -> bool:
        """브라우저를 한 번 켜서 500개를 채우거나 세션이 끊길 때까지 수집합니다.

        Returns:
            브라우저 세션이 중간에 끊겨서 중단된 경우 True,
            정상적으로(500개 도달 또는 더 이상 로드할 리뷰 없음) 종료된 경우 False.
        """
        self.start_browser()
        if not self.driver:
            raise RuntimeError("WebDriver가 정상적으로 초기화되지 않았습니다.")

        list_selector = self._locate_review_list_selector(timeout=5)

        if list_selector is None:
            print("[디버그] top-level에서 리뷰 목록을 못 찾음. iframe 탐색 시도...")
            found_frame = self._find_review_iframe()
            if found_frame is not None:
                self._in_iframe = True
                list_selector = self._locate_review_list_selector(timeout=10)

        if list_selector is None:
            debug_path = os.path.join(self.output_dir, "debug_page_source.html")
            os.makedirs(self.output_dir, exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self.driver.quit()
            raise RuntimeError(
                "리뷰 목록 요소를 찾지 못했습니다. "
                f"'{debug_path}' 파일에 현재 페이지의 HTML을 저장했으니 확인해 주세요."
            )

        print(f"[디버그] 사용할 리스트 셀렉터: {list_selector} (iframe 내부 여부: {self._in_iframe})")

        session_lost = False

        try:
            stagnant_rounds = 0  # 스크롤해도 새 리뷰가 안 늘어난 연속 횟수
            max_stagnant_rounds = 5  # 이 횟수만큼 연속으로 안 늘어나면 종료

            while len(self.reviews) < 500:
                try:
                    review_elements = self.driver.find_elements(By.CSS_SELECTOR, f"{list_selector} > li")
                except InvalidSessionIdException:
                    print(
                        "\n[오류] 브라우저 세션이 끊겼습니다 (브라우저 창이 닫혔거나, "
                        "PC가 절전모드로 전환됐거나, Chrome이 자동 업데이트로 재시작됐을 수 있습니다). "
                        "지금까지 모은 데이터를 저장합니다."
                    )
                    session_lost = True
                    break

                print(f"[디버그] 현재 로드된 리뷰 li 개수: {len(review_elements)} / 누적 수집: {len(self.reviews)}")

                start_index = len(self.reviews)
                newly_parsed = 0
                for element in review_elements[start_index:]:
                    if len(self.reviews) >= 500:
                        break

                    try:
                        rating = self._extract_rating(element)
                        date_text = self._extract_date(element)
                        content_text = self._extract_content(element)

                        if content_text is None:
                            continue

                        # 중복 체크: 날짜 + 본문 앞 80자를 키로 사용
                        dedup_key = (date_text, content_text[:80])
                        if dedup_key in self._seen_keys:
                            continue
                        self._seen_keys.add(dedup_key)

                        self.reviews.append({
                            "rating": rating,
                            "date": date_text,
                            "content": content_text,
                        })
                        newly_parsed += 1
                        print(f"[{len(self.reviews)}/500] 수집 완료 - 별점: {rating} | 날짜: {date_text}")

                        # 중간 자동 저장 (세션이 끊겨도 지금까지 모은 데이터는 보존)
                        if len(self.reviews) - self._last_autosave_count >= self.autosave_every:
                            self.save_to_database()
                            self._last_autosave_count = len(self.reviews)

                        time.sleep(self.request_delay)

                    except StaleElementReferenceException:
                        continue
                    except (InvalidSessionIdException, WebDriverException) as e:
                        print(
                            "\n[오류] 리뷰 파싱 도중 브라우저 세션이 끊겼습니다. "
                            "지금까지 모은 데이터를 저장합니다.\n"
                            f"(원인: {e.__class__.__name__})"
                        )
                        session_lost = True
                        break
                    except Exception as e:
                        print(f"[경고] 개별 리뷰 파싱 실패: {e}")
                        continue

                if session_lost:
                    break

                if len(self.reviews) >= 500:
                    break

                # 새로 파싱된 리뷰가 없었다면(=화면에 새로 로드된 li가 없었다면)
                # 스크롤을 내려서 다음 페이지를 로드 시도
                count_before_scroll = len(review_elements)
                try:
                    loaded_more = self._scroll_to_load_more(list_selector, count_before_scroll)
                except (InvalidSessionIdException, WebDriverException) as e:
                    print(
                        "\n[오류] 스크롤 도중 브라우저 세션이 끊겼습니다. "
                        "지금까지 모은 데이터를 저장합니다.\n"
                        f"(원인: {e.__class__.__name__})"
                    )
                    session_lost = True
                    break

                if not loaded_more:
                    stagnant_rounds += 1
                    print(f"[디버그] 스크롤해도 새 리뷰가 로드되지 않음 ({stagnant_rounds}/{max_stagnant_rounds})")
                    if stagnant_rounds >= max_stagnant_rounds:
                        print("[디버그] 더 이상 로드할 리뷰가 없는 것으로 판단하여 종료합니다.")
                        break
                else:
                    stagnant_rounds = 0

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass  # 이미 죽은 세션을 quit()하면 에러가 나지만 무시해도 안전함
                self.driver = None

            # 세션이 끊겼든 정상 종료든, 그동안 모은 데이터는 항상 저장
            if self.reviews:
                self.save_to_database()

        return session_lost

    def _find_scrollable_ancestor_info(self, list_selector: str) -> None:
        """리스트의 조상 요소들 중 실제로 스크롤이 걸리는(overflow) 요소를 찾아 로그로 출력합니다.

        진단용입니다. window 스크롤이 안 먹힐 때, 어떤 내부 div가 자체 스크롤
        컨테이너인지 알아내기 위해 사용합니다.
        """
        assert self.driver is not None
        try:
            info = self.driver.execute_script(
                """
                const listEl = document.querySelector(arguments[0]);
                if (!listEl) return null;
                let el = listEl;
                const results = [];
                while (el && el !== document.body) {
                    const style = window.getComputedStyle(el);
                    const scrollable = el.scrollHeight > el.clientHeight + 5;
                    results.push({
                        tag: el.tagName,
                        cls: el.className,
                        overflowY: style.overflowY,
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        scrollable: scrollable
                    });
                    el = el.parentElement;
                }
                return results;
                """,
                list_selector,
            )
            if info:
                for row in info:
                    if row.get("scrollable"):
                        print(f"[디버그] 스크롤 가능한 조상 발견: <{row['tag']} class='{row['cls']}'> "
                              f"overflow-y={row['overflowY']} scrollHeight={row['scrollHeight']} "
                              f"clientHeight={row['clientHeight']}")
        except Exception as e:
            print(f"[디버그] 스크롤 컨테이너 진단 실패: {e}")

    def _scroll_to_load_more(self, list_selector: str, previous_count: int, max_attempts: int = 3) -> bool:
        """무한 스크롤로 추가 리뷰를 로드합니다. 여러 스크롤 전략을 순서대로 시도합니다.

        가장 먼저 '진짜' 마우스 휠 스크롤 이벤트(ActionChains)를 시도합니다.
        JS의 window.scrollTo/scrollIntoView는 브라우저 입력 파이프라인을 거치지
        않는 '가짜' 스크롤이라, wheel/scroll 네이티브 이벤트를 감지하는 무한 스크롤
        구현체는 반응하지 않는 경우가 많습니다. ActionChains.scroll_by_amount는
        실제 트랙패드/마우스 휠과 동일한 이벤트를 발생시켜 훨씬 잘 작동합니다.

        Args:
            list_selector: 리뷰 리스트 컨테이너 CSS 셀렉터
            previous_count: 스크롤 전 로드되어 있던 리뷰 li 개수
            max_attempts: 각 전략별 재시도 최대 횟수

        Returns:
            새 리뷰가 로드되면 True, 끝까지 안 늘어나면 False
        """
        assert self.driver is not None

        def current_count() -> int:
            return len(self.driver.find_elements(By.CSS_SELECTOR, f"{list_selector} > li"))

        # 전략 1 (최우선): 실제 마우스 휠 스크롤 이벤트 (native wheel event)
        try:
            for attempt in range(max_attempts):
                ActionChains(self.driver).scroll_by_amount(0, 900).perform()
                time.sleep(0.8)
                if current_count() > previous_count:
                    print(f"[디버그] [전략1: 실제 휠 스크롤] 리뷰 {current_count() - previous_count}개 추가 로드됨")
                    return True
        except Exception as e:
            print(f"[디버그] 전략1(휠 스크롤) 실행 불가 (Selenium 버전이 낮을 수 있음): {e}")

        # 전략 2: 마지막 li 요소를 대상으로 실제 휠 스크롤 (IntersectionObserver 대응)
        try:
            items = self.driver.find_elements(By.CSS_SELECTOR, f"{list_selector} > li")
            if items:
                last_item = items[-1]
                for attempt in range(max_attempts):
                    ActionChains(self.driver).scroll_to_element(last_item).perform()
                    ActionChains(self.driver).scroll_by_amount(0, 600).perform()
                    time.sleep(0.8)
                    if current_count() > previous_count:
                        print(f"[디버그] [전략2: 마지막 li로 휠 스크롤] 리뷰 {current_count() - previous_count}개 추가 로드됨")
                        return True
        except Exception as e:
            print(f"[디버그] 전략2 실행 중 오류: {e}")

        # 전략 3: window.scrollTo (JS 기반, 폴백)
        for attempt in range(max_attempts):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.0)
            if current_count() > previous_count:
                print(f"[디버그] [전략3: window.scrollTo] 리뷰 {current_count() - previous_count}개 추가 로드됨")
                return True

        # 전략 4: 자체 스크롤 컨테이너(overflow 요소)를 찾아 그 안에서 스크롤
        try:
            scrolled = self.driver.execute_script(
                """
                const listEl = document.querySelector(arguments[0]);
                if (!listEl) return false;
                let el = listEl;
                while (el && el !== document.body) {
                    const style = window.getComputedStyle(el);
                    if (el.scrollHeight > el.clientHeight + 5 &&
                        (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                        el.scrollTop = el.scrollHeight;
                        el.dispatchEvent(new Event('scroll', { bubbles: true }));
                        return true;
                    }
                    el = el.parentElement;
                }
                return false;
                """,
                list_selector,
            )
            if scrolled:
                time.sleep(1.0)
                if current_count() > previous_count:
                    print(f"[디버그] [전략4: 내부 스크롤 컨테이너] 리뷰 {current_count() - previous_count}개 추가 로드됨")
                    return True
        except Exception as e:
            print(f"[디버그] 전략4 실행 중 오류: {e}")

        # 여기까지 다 실패하면 진단 정보 출력 (한 번만, 너무 자주 찍히지 않도록)
        print("[디버그] 모든 스크롤 전략 실패. 스크롤 가능한 컨테이너 진단 중...")
        self._find_scrollable_ancestor_info(list_selector)
        return False

    def _extract_rating(self, element: WebElement) -> float:
        """별점을 추출합니다.

        구조: span.starred_grade 안에 span.screen_out 이 2개 있는데,
        첫 번째는 '별점'이라는 라벨이고 두 번째가 실제 숫자 값('5.0' 등)입니다.
        숫자로 파싱 가능한 screen_out 텍스트를 찾아 사용하고,
        실패하면 span.figure_star.on 개수로 대체합니다.
        """
        try:
            starred = element.find_element(By.CSS_SELECTOR, "span.starred_grade")
        except NoSuchElementException:
            return 0.0

        screen_outs = starred.find_elements(By.CSS_SELECTOR, "span.screen_out")
        for span in screen_outs:
            text = span.text.strip()
            match = re.match(r"^\d+(\.\d+)?$", text)
            if match:
                return round(float(text), 1)

        # 폴백: 채워진 별(figure_star.on) 개수로 계산
        try:
            filled_stars = starred.find_elements(By.CSS_SELECTOR, "span.wrap_grade span.figure_star.on")
            if filled_stars:
                return float(len(filled_stars))
        except NoSuchElementException:
            pass

        return 0.0

    def _extract_date(self, element: WebElement) -> str:
        """날짜를 추출합니다. 끝의 마침표는 제거합니다 (예: '2026.07.01.' -> '2026.07.01')."""
        candidates = ["span.txt_date", "span.time_write"]
        for sel in candidates:
            try:
                text = element.find_element(By.CSS_SELECTOR, sel).text.strip()
                return text.rstrip(".")
            except NoSuchElementException:
                continue
        return ""

    def _extract_content(self, element: WebElement) -> Optional[str]:
        """리뷰 본문을 추출합니다.

        본문이 길면 '더보기' 링크로 잘려 보일 수 있어, 먼저 확장을 시도한 뒤
        a.link_review 의 텍스트를 가져옵니다.
        """
        # 리뷰 내 '더보기' 토글이 있으면 클릭해서 전체 텍스트를 펼침
        for more_sel in ["a.btn_more", "span.btn_more", "a.link_more_review"]:
            try:
                more_el = element.find_element(By.CSS_SELECTOR, more_sel)
                element.parent.execute_script("arguments[0].click();", more_el)
            except NoSuchElementException:
                continue
            except Exception:
                continue

        candidates = ["a.link_review", "p.txt_comment > span", "p.txt_comment", "div.txt_review"]
        for sel in candidates:
            try:
                text = element.find_element(By.CSS_SELECTOR, sel).text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue
        return None

    def save_to_database(self) -> None:
        """수집된 리뷰 데이터를 CSV 형식으로 저장합니다."""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        file_path = os.path.join(self.output_dir, "reviews_kakao.csv")
        df = pd.DataFrame(self.reviews)
        df.to_csv(file_path, index=False, encoding="utf-8-sig")
        print(f"성공적으로 데이터를 저장했습니다: {file_path} (총 {len(self.reviews)}개)")


if __name__ == "__main__":
    crawler = KakaoCrawler(output_dir="./data", request_delay=0.5, headless=False)
    crawler.scrape_reviews()
    crawler.save_to_database()