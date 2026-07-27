# YBIGTA_newbie_team_project

## 팀 소개
안녕하세요 YBIGTA 신입기수 세션 6조입니다.

## 팀원 자기소개
- **권준범**: 응용정보공학과 23학번, 04년생
- **나예린**: 도시공학과 24학번, 05년생
- **박형민**: (학과, 학번, 출생년도 등 한 줄 부탁드려요!)

## GitHub 협업 과정 (4회차)

### Branch Protection Rule 적용
_(캡처본 추가 예정)_
<!-- ![branch protection](github/branch_protection.png) -->

### Main 브랜치 Push 거부 확인
_(캡처본 추가 예정)_
<!-- ![push rejected](github/push_rejected.png) -->

### PR + Review + Merge
![review and merged](github/review_and_merged.png)

## 과제 실행 방법

### 1. Web
FastAPI와 MVC 패턴을 기반으로 사용자 로그인 기능 구현

- **index.html 꾸미기**: 다크모드 스타일링 등 시각적 요소 추가
- **user_service.py**: 로그인, 회원가입, 삭제, 비밀번호 변경에 대한 비즈니스 로직과 예외 처리 구현
- **user_router.py**: 아래 4개 API 엔드포인트 구현
  - `POST /api/user/login` - 로그인
  - `POST /api/user/register` - 회원가입
  - `DELETE /api/user/delete` - 회원 삭제
  - `PUT /api/user/update-password` - 비밀번호 변경

### 2. 크롤링
<왕과 사는 남자> 영화에 대해 세 개 사이트에서 리뷰 데이터 수집

- **메가박스**: 별점(10점 만점), 작성일, 리뷰 내용 510개 수집, `database/reviews_megabox.csv`에 저장
- **Kinolights**: 별점(5점 만점), 작성일, 리뷰 내용 505개 수집, `database/reviews_kinolights.csv`에 저장
- **네이버 영화 관람평**: 별점(5점 만점), 작성일, 리뷰 내용 500개 수집, `database/reviews_naver.csv`에 저장
- 리뷰 내용이 비어있는 관람평은 최소조건(별점/날짜/내용 모두 포함) 충족을 위해 수집에서 제외

### 3. EDA·FE
크롤링한 세 사이트의 리뷰 데이터를 대상으로 개별 분석과 사이트간 비교분석 진행

- **EDA**: 별점, 텍스트 길이, 날짜의 분포와 이상치 파악
- **데이터 전처리/FE**: 사이트별 별점·날짜 형식 통일, 결측치·이상치 제거, 텍스트 전처리 진행, 파생변수로 요일 추출, TF-IDF 평균 점수 두 가지 생성
- **비교분석**: 감성분석, 키워드 분석, 시계열 분석을 통해 사이트간 차이 비교

---

# [3회차] 크롤링 과제 - &lt;왕과 사는 남자&gt; 리뷰 수집

## 데이터 소개

### 메가박스 (나예린)

- **사이트 링크**: https://www.megabox.co.kr/movie-detail/comment?rpstMovieNo=25104500
- **데이터 형식**: `rating`(별점, 10점 만점), `date`(작성일, YYYY-MM-DD), `content`(리뷰 내용)
- **수집 개수**: 510개
- **저장 위치**: `database/reviews_megabox.csv`
- **비고**: 리뷰 내용이 비어있는 관람평(별점만 남긴 경우)은 최소조건(별점/날짜/내용 모두 포함)을 만족시키기 위해 수집에서 제외했습니다.

### Kinolights (권준범)

- **사이트 링크**: https://m.kinolights.com/season/148606/reviews
- **데이터 형식**: `rating`(별점, 5점 만점), `date`(작성일, YYYY-MM-DD), `content`(리뷰 내용)
- **수집 개수**: 505개
- **저장 위치**: `database/reviews_kinolights`
- **비고**: 리뷰 내용이 비어있는 관람평(별점만 남긴 경우)은 최소조건(별점/날짜/내용 모두 포함)을 만족시키기 위해 수집에서 제외했습니다.


### 네이버 영화 관람평 (박형민)

- **사이트 링크**: https://search.naver.com/search.naver?where=nexearch&sm=tab_etc&mra=bkEw&pkid=68&os=35442190&qvt=0&query=%EC%99%95%EA%B3%BC%20%EC%82%AC%EB%8A%94%20%EB%82%A8%EC%9E%90%20%EA%B4%80%EB%9E%8C%ED%8F%89
- **데이터 형식**: `rating`(별점, 5점 만점), `date`(작성일, YYYY-MM-DD 00:00:00 AM/PM), `content`(리뷰 내용)
- **수집 개수**: 500
- **저장 위치**: `database/reviews_naver.csv`

## 실행 방법

### 0. 필요한 패키지 설치

```bash
pip install beautifulsoup4 selenium pandas scikit-learn kiwipiepy matplotlib
```

### 1. 전체 크롤러 한 번에 실행

프로젝트 루트(`README.md`가 있는 위치)에서 아래 명령어 실행 시,
`CRAWLER_CLASSES`에 등록된 모든 크롤러가 순서대로 실행되어
각자의 결과 CSV가 지정한 output_path에 저장됨

```bash
python -m review_analysis.crawling.main -o {output_path} --all
```

예시:

```bash
python -m review_analysis.crawling.main -o database --all
```

### 2. 특정 크롤러 하나만 실행

```bash
python -m review_analysis.crawling.main -o database --crawler megabox
```

예시 (메가박스만 실행):

```bash
python -m review_analysis.crawling.main -o {output_path} --crawler {크롤러 이름}
```

`{크롤러 이름}`에는 `review_analysis/crawling/main.py`의 `CRAWLER_CLASSES` 딕셔너리에 
등록된 이름(`example`, `megabox` 등) 사용

### 3. 브라우저 창 실행 안내

Selenium이 Edge, Chrome 브라우저를 직접 실행하여 크롤링 진행
실행 중 브라우저 창 유지 필수(임의 종료 금지)
크롤링 종료 시 브라우저 자동 종료

---

# [4회차] EDA&FE, 시각화 과제 - &lt;왕과 사는 남자&gt; 리뷰 분석

## 1. EDA


## 2. 전처리/FE


## 3. 비교분석

### 키워드 분석:

### 감성분석:

### 시계열 분석: 사이트별 평점 및 리뷰 개수 추이

![평점 추이 비교](review_analysis/plots/rating_trend_comparison.png)
![리뷰 개수 추이 비교](review_analysis/plots/review_count_trend_comparison.png)

**분석 방법**
- 각 사이트의 일별 평균 평점 및 일별 리뷰 개수를 계산한 뒤, 리뷰 유입이 없는 날의 노이즈를 완화하기 위해 7일 이동평균(rolling mean)을 적용해 추이를 시각화함
- 세 사이트(kinolights, megabox, naver)의 크롤링 시점이 서로 달라 전체 기간(2026-02-04 ~ 2026-07-25)을 기준으로 겹쳐서 비교함

**주요 발견**
1. **naver**: 개봉 초반(2월) 평점이 5점에 가깝게 높게 형성되었다가, 시간이 지나며 꾸준히 하락해 1점대까지 떨어지는 뚜렷한 하락 추세를 보임. 동시에 리뷰 개수도 초반 하루 100개 이상 폭발적으로 몰렸다가 이후 급격히 감소함 — 개봉 직후 기대감 섞인 리뷰가 대거 유입되고, 이후 냉정한 평가로 전환된 것으로 추정됨
2. **megabox**: 관측 기간(5~7월) 내내 평점이 4.3~4.8 사이로 안정적으로 유지됨.
실관람객 인증 기반 리뷰 시스템의 영향으로 추정되며, 리뷰 개수도 하루 5~20개 수준으로 꾸준히 유입됨
3. **kinolights**: 3~4점대에서 뚜렷한 추세 없이 등락을 반복함. 리뷰 개수 자체가 적어(하루 1~5개) 이동평균으로도 노이즈가 다소 남아있음

**시사점**: 동일 영화(&lt;왕과 사는 남자&gt;)에 대한 평가라도, 플랫폼의 리뷰 작성 방식(실관람객 인증 여부, 리뷰 유입 시점)에 따라 평점 추이 패턴이 뚜렷하게 달라짐을 확인함