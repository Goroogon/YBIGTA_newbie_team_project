import os
import re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from kiwipiepy import Kiwi
from review_analysis.preprocessing.base_processor import BaseDataProcessor


# 형태소 분석기는 초기화 비용이 있으므로 모듈 로드 시 한 번만 생성해 재사용
# (Java/JVM 불필요, pip install만으로 동작하는 순수 C++ 기반 분석기)
_kiwi = Kiwi()

# 제거할 품사 태그의 접두사 (세종 품사 태그 체계 기준)
# J*: 조사(JKS, JKB, JX ...), E*: 어미(EP, EF, EC ...), S*: 문장부호(SF, SP ...)
STOPWORD_TAG_PREFIXES = ('J', 'E', 'S')
# 접사/감탄사 등 개별 태그로 제거할 것들
STOPWORD_TAGS = {'XSN', 'XSV', 'XSA', 'IC'}

# 형태소 분석 후에도 남을 수 있는 의미 없는 단어(불완전 명사 등) 목록
STOPWORDS_KO = {
    '이', '그', '저', '것', '수', '등', '들', '및', '의', '가',
    '은', '는', '을', '를', '에', '와', '과', '도',
    '한', '거', '더', '좀', '진짜', '정말', '너무',
}


class SiteProcessor(BaseDataProcessor):
    def __init__(self, input_path: str, output_dir: str = "database", site_name: str = None):
        super().__init__(input_path, output_dir)
        # site_name을 명시하지 않으면 입력 파일명에서 자동 추출
        # 예: reviews_naver.csv -> naver (파일명 앞의 'reviews_' 접두사는 제거)
        if site_name:
            self.site_name = site_name
        else:
            base = os.path.splitext(os.path.basename(input_path))[0]
            self.site_name = re.sub(r'^reviews_', '', base, flags=re.IGNORECASE)
        # raw 리뷰 데이터 로드
        self.df = pd.read_csv(self.input_path)

    def preprocess(self):
        """
        1. 결측치 처리, 이상치 처리, 날짜 형식 정제, 텍스트 전처리 수행
        """
        # ==========================================
        # [1] 결측치 처리 (Missing Values)
        # ==========================================
        # 별점(rating), 리뷰(content), 날짜(date)가 없는 행 제거
        self.df.dropna(subset=['rating', 'content', 'date'], inplace=True)

        # ==========================================
        # [2] 별점 스케일링 및 이상치 처리 (Rating Scaling & Outliers)
        # ==========================================
        self.df['rating'] = pd.to_numeric(self.df['rating'], errors='coerce')

        # 10점 척도로 입력된 별점(5 초과)을 5점 척도로 스케일링 (예: 8점 -> 4.0점)
        self.df['rating'] = self.df['rating'].apply(
            lambda x: x / 2 if pd.notna(x) and x > 5 else x
        )

        # 스케일링 이후에도 1~5 범위를 벗어나는 값은 이상치로 간주하여 제거
        # (예: 원본이 10점을 초과하는 경우 -> 스케일링 후에도 5점 초과)
        self.df = self.df[(self.df['rating'] >= 1) & (self.df['rating'] <= 5)]

        # ==========================================
        # [3] 날짜 형식 전처리 (Dates)
        # ==========================================
        # 날짜 포맷 통일 ('2026-04-30 11:02:00 PM' 및 '2026-07-24' -> 'YYYY-MM-DD')
        self.df['date_parsed'] = pd.to_datetime(self.df['date'], format='mixed', errors='coerce')

        # 날짜 변환 실패한 이상치(NaT) 제거
        self.df.dropna(subset=['date_parsed'], inplace=True)

        # 'YYYY-MM-DD' 형식의 문자열로 변환하여 date 컬럼 갱신
        self.df['date'] = self.df['date_parsed'].dt.strftime('%Y-%m-%d')

        # 이상치 판별용으로만 쓰인 임시 컬럼이므로 삭제
        self.df.drop(columns=['date_parsed'], inplace=True)

        # ==========================================
        # [4] 텍스트 데이터 전처리 (Text Preprocessing)
        # ==========================================
        # 이모지(이모티콘) 유니코드 범위 패턴
        emoji_pattern = re.compile(
            "["
            "\U0001F300-\U0001FAFF"  # 기호, 그림문자, 확장 이모지
            "\U00002600-\U000027BF"  # 기타 기호 및 딩뱃
            "\U0001F1E6-\U0001F1FF"  # 국기(지역 표시 기호)
            "\U00002190-\U000021FF"  # 화살표
            "\U00002B00-\U00002BFF"  # 기타 화살표/기호
            "]+",
            flags=re.UNICODE
        )

        def _clean_text(text: str) -> str:
            if not isinstance(text, str):
                return ""

            # (a) 이모티콘 제거
            text = emoji_pattern.sub(' ', text)

            # (b) 한글 자음/모음만 단독으로 쓰인 문자 제거 (예: ㅋㅋㅋ, ㅠㅠ, ㅎㅎ)
            #     완성형 한글 음절(가-힣)이 아닌 낱자모(ㄱ-ㅎ, ㅏ-ㅣ)만 제거
            text = re.sub(r'[ㄱ-ㅎㅏ-ㅣ]+', ' ', text)

            # (c) 그 외 특수문자 제거 (한글 완성형, 영문, 숫자, 공백 외 모두 제거)
            text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', text)

            # (d) 연속 공백 정리
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        self.df['cleaned_review'] = self.df['content'].apply(_clean_text)

        # ==========================================
        # [5] 불용어 제거 (형태소 분석 기반, Kiwi)
        # ==========================================
        # 단순 공백 split이 아니라 형태소 단위로 분리 -> 조사/어미가 단어에
        # 붙어있어도('박지훈도' -> '박지훈' + '도') 정확히 분리해서 제거 가능.
        def _remove_stopwords(text: str) -> str:
            if not text:
                return ""
            tokens = _kiwi.tokenize(text)
            words = [
                t.form for t in tokens
                if not t.tag.startswith(STOPWORD_TAG_PREFIXES)
                and t.tag not in STOPWORD_TAGS
                and t.form not in STOPWORDS_KO
            ]
            return ' '.join(words)

        self.df['cleaned_review'] = self.df['cleaned_review'].apply(_remove_stopwords)

        # 비정상적으로 길거나 짧은 리뷰 이상치 제거 (예: 5자 미만 제거)
        # -> 자음/이모티콘만 있던 리뷰는 위 클리닝 단계에서 빈 문자열이 되어 여기서 함께 제거됨
        self.df['text_len'] = self.df['cleaned_review'].str.len()
        self.df = self.df[self.df['text_len'] >= 5]
        self.df.drop(columns=['text_len'], inplace=True)

        self.df.reset_index(drop=True, inplace=True)

    def feature_engineering(self):
        """
        2. 파생 변수 생성 및 텍스트 벡터화 수행
        """
        # ==========================================
        # [1] 파생 변수 생성
        # ==========================================
        # 요일 파생변수만 생성 (요청에 따라 year_month, review_length 등은 제거)
        date_obj = pd.to_datetime(self.df['date'])
        self.df['day_of_week'] = date_obj.dt.day_name()

        # ==========================================
        # [2] 텍스트 벡터화 (Text Vectorization)
        # ==========================================
        # TF-IDF 벡터화 수행
        self.tfidf_vectorizer = TfidfVectorizer(max_features=10)
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.df['cleaned_review']).toarray()

        # 리뷰별 TF-IDF 점수 평균을 컬럼으로 저장 (확인 가능하도록)
        self.df['tf_idf_mean_score'] = self.tfidf_matrix.mean(axis=1)

    def save_to_database(self):
        """
        3. preprocessed_reviews_{사이트이름}.csv 파일로 지정 경로에 저장
        """
        os.makedirs(self.output_dir, exist_ok=True)

        # 저장 시 컬럼 순서 지정
        column_order = ['date', 'rating', 'content', 'cleaned_review', 'day_of_week', 'tf_idf_mean_score']
        self.df = self.df[column_order]

        # 파일명 지정: preprocessed_reviews_{사이트이름}.csv (site_name은 생성자에서 결정됨)
        output_filename = f"preprocessed_reviews_{self.site_name}.csv"
        output_path = os.path.join(self.output_dir, output_filename)

        self.df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"[SUCCESS] Saved preprocessed data to: {output_path}")