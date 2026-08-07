import os
import re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from kiwipiepy import Kiwi
from review_analysis.preprocessing.base_processor import BaseDataProcessor


_kiwi = Kiwi()

STOPWORD_TAG_PREFIXES = ('J', 'E', 'S')
STOPWORD_TAGS = {'XSN', 'XSV', 'XSA', 'IC'}

STOPWORDS_KO = {
    '이', '그', '저', '것', '수', '등', '들', '및', '의', '가',
    '은', '는', '을', '를', '에', '와', '과', '도',
    '한', '거', '더', '좀', '진짜', '정말', '너무',
}


class SiteProcessor(BaseDataProcessor):
    def __init__(self, input_path: str = None, output_dir: str = "database",
                 site_name: str = None, df: pd.DataFrame = None):
        super().__init__(input_path, output_dir)

        if site_name:
            self.site_name = site_name
        elif input_path:
            base = os.path.splitext(os.path.basename(input_path))[0]
            self.site_name = re.sub(r'^reviews_', '', base, flags=re.IGNORECASE)
        else:
            self.site_name = "unknown"

        if df is not None:
            self.df = df.copy()
        elif input_path:
            self.df = pd.read_csv(self.input_path)
        else:
            raise ValueError("input_path 또는 df 중 하나는 반드시 제공되어야 합니다.")

    def preprocess(self):
        self.df.dropna(subset=['rating', 'content', 'date'], inplace=True)

        self.df['rating'] = pd.to_numeric(self.df['rating'], errors='coerce')
        self.df['rating'] = self.df['rating'].apply(
            lambda x: x / 2 if pd.notna(x) and x > 5 else x
        )
        self.df = self.df[(self.df['rating'] >= 0.5) & (self.df['rating'] <= 5)]

        self.df['date_parsed'] = pd.to_datetime(self.df['date'], format='mixed', errors='coerce')
        self.df.dropna(subset=['date_parsed'], inplace=True)
        self.df['date'] = self.df['date_parsed'].dt.strftime('%Y-%m-%d')
        self.df.drop(columns=['date_parsed'], inplace=True)

        emoji_pattern = re.compile(
            "["
            "\U0001F300-\U0001FAFF"
            "\U00002600-\U000027BF"
            "\U0001F1E6-\U0001F1FF"
            "\U00002190-\U000021FF"
            "\U00002B00-\U00002BFF"
            "]+",
            flags=re.UNICODE
        )

        def _clean_text(text: str) -> str:
            if not isinstance(text, str):
                return ""
            text = emoji_pattern.sub(' ', text)
            text = re.sub(r'[ㄱ-ㅎㅏ-ㅣ]+', ' ', text)
            text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        self.df['cleaned_review'] = self.df['content'].apply(_clean_text)

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

        self.df['text_len'] = self.df['cleaned_review'].str.len()
        self.df = self.df[self.df['text_len'] >= 5]
        self.df.drop(columns=['text_len'], inplace=True)

        self.df.reset_index(drop=True, inplace=True)

    def feature_engineering(self):
        date_obj = pd.to_datetime(self.df['date'])
        self.df['day_of_week'] = date_obj.dt.day_name()

        self.tfidf_vectorizer = TfidfVectorizer(max_features=10)
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.df['cleaned_review']).toarray()
        self.df['tf_idf_mean_score'] = self.tfidf_matrix.mean(axis=1)

    def save_to_database(self):
        os.makedirs(self.output_dir, exist_ok=True)

        column_order = ['date', 'rating', 'content', 'cleaned_review', 'day_of_week', 'tf_idf_mean_score']
        self.df = self.df[column_order]

        output_filename = f"preprocessed_reviews_{self.site_name}.csv"
        output_path = os.path.join(self.output_dir, output_filename)

        self.df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"[SUCCESS] Saved preprocessed data to: {output_path}")

    def to_records(self) -> list:
        """MongoDB 저장용 (신규): dict 리스트로 반환"""
        column_order = ['date', 'rating', 'content', 'cleaned_review', 'day_of_week', 'tf_idf_mean_score']
        self.df = self.df[column_order]
        return self.df.to_dict('records')