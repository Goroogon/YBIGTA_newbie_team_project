# [3회차] 크롤링 과제 - &lt;왕과 사는 남자&gt; 리뷰 수집

## 데이터 소개

### 메가박스 (예린)

- **사이트 링크**: https://www.megabox.co.kr/movie-detail/comment?rpstMovieNo=25104500
- **데이터 형식**: `rating`(별점, 10점 만점), `date`(작성일, YYYY-MM-DD), `content`(리뷰 내용)
- **수집 개수**: 510개
- **저장 위치**: `database/reviews_megabox.csv`
- **비고**: 리뷰 내용이 비어있는 관람평(별점만 남긴 경우)은 최소조건(별점/날짜/내용 모두 포함)을 만족시키기 위해 수집에서 제외했습니다.

### (팀원 이름 - 사이트명)

- **사이트 링크**: (작성 예정)
- **데이터 형식**: (작성 예정)
- **수집 개수**: (작성 예정)
- **저장 위치**: `database/reviews_(사이트명).csv`

### (팀원 이름 - 사이트명)

- **사이트 링크**: (작성 예정)
- **데이터 형식**: (작성 예정)
- **수집 개수**: (작성 예정)
- **저장 위치**: `database/reviews_(사이트명).csv`

## 실행 방법

### 0. 필요한 패키지 설치

```bash
pip install beautifulsoup4 selenium pandas
```

### 1. 전체 크롤러 한 번에 실행

프로젝트 루트(`README.md`가 있는 위치)에서 아래 명령어를 실행하면
`CRAWLER_CLASSES`에 등록된 모든 크롤러가 순서대로 실행되어,
각자의 결과 CSV가 지정한 output_path에 저장됩니다.

```bash
python main.py -o {output_path} --all
```

예시:

```bash
python main.py -o database --all
```

### 2. 특정 크롤러 하나만 실행

```bash
python main.py -o {output_path} -c {크롤러 이름}
```

예시 (메가박스만 실행):

```bash
python main.py -o database -c megabox
```

`{크롤러 이름}`에는 `review_analysis/crawling/main.py`의 `CRAWLER_CLASSES` 딕셔너리에
등록된 이름(`example`, `megabox` 등)을 사용합니다.

### 3. 실행 시 브라우저 창이 열립니다

Selenium이 Edge 브라우저를 직접 실행하여 크롤링을 진행하므로,
실행 중에는 브라우저 창을 닫지 말고 그대로 두어야 합니다.
크롤링이 끝나면 브라우저가 자동으로 종료됩니다.
