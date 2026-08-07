# -*- coding: utf-8 -*-
"""
한국어 감성사전(Lexicon) 기반 감성분석 - 다중 파일 처리 버전
- cleaned_review: 형태소 단위로 공백 분리된 전처리 완료 텍스트
- 감성사전의 단어 점수를 이용해 리뷰의 감성(긍정/부정/중립)을 판별한다.
- 여러 개의 리뷰 CSV 파일을 한 번에 순회하며 처리하고,
  파일별 결과 + 전체 파일을 비교하는 요약 결과를 함께 만든다.

사전 파일 형식:
    단어(또는 어구)    극성점수
    예)
    좋다    2
    최고    2
    최악    -2

    - 구분자는 tab, space, comma 어느 것이든 자동으로 인식합니다.
    - 극성 점수는 보통 -2 ~ +2 (혹은 -1/0/1) 범위의 정수/실수를 사용합니다.
"""

import os
import glob
from collections import Counter
from typing import Optional


import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

# ------------------------------------------------------------------
# 0. 경로 설정 (여기만 바꿔서 쓰면 됩니다)
# ------------------------------------------------------------------
DATA_PATHS = [
    "database/preprocessed_reviews_naver.csv",
    "database/preprocessed_reviews_megabox.csv",
    "database/preprocessed_reviews_kinolights.csv",
]

DICT_PATH = "review_analysis/plots/SentiWord_Dict.txt"   # 감성사전 파일 경로
PLOTS_DIR = "review_analysis/plots"                       # 그래프/결과 csv 저장 폴더

os.makedirs(PLOTS_DIR, exist_ok=True)

# ------------------------------------------------------------------
# 0-1. 한글 폰트 설정 (그래프 한글 깨짐 방지)
#      운영체제별로 흔히 설치돼 있는 한글 폰트 후보들을 순서대로 시도해서
#      실제로 존재하는 첫 번째 폰트를 사용한다.
# ------------------------------------------------------------------
def setup_korean_font():
    candidates = [
        # Windows
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/malgunbd.ttf",
        # macOS
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        # Linux (Colab, Ubuntu 등)
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                font_prop = fm.FontProperties(fname=path)
                fm.fontManager.addfont(path)
                plt.rcParams["font.family"] = font_prop.get_name()
                print(f"[폰트] 사용 중: {path}")
                return
            except Exception:
                continue

    # 후보 경로에 없다면, 시스템에 설치된 폰트 중 한글 지원 폰트를 이름으로 탐색
    name_candidates = [
        "Malgun Gothic", "AppleGothic", "NanumGothic",
        "Noto Sans CJK KR", "Noto Sans KR", "Apple SD Gothic Neo",
    ]
    installed = {f.name for f in fm.fontManager.ttflist}
    for name in name_candidates:
        if name in installed:
            plt.rcParams["font.family"] = name
            print(f"[폰트] 사용 중: {name}")
            return

    print(
        "[경고] 한글 폰트를 찾지 못했습니다. 그래프의 한글이 깨져 보일 수 있습니다.\n"
        "  - Windows: 보통 자동으로 잡힙니다. 안 되면 'Malgun Gothic' 설치 여부 확인\n"
        "  - Mac: 'AppleGothic' 폰트 확인\n"
        "  - Linux/Colab: `apt-get install -y fonts-nanum` 후 다시 실행하거나,\n"
        "    나눔고딕을 다운로드해 candidates 리스트에 경로를 추가하세요."
    )


setup_korean_font()
plt.rcParams["axes.unicode_minus"] = False


# ------------------------------------------------------------------
# 1. 감성사전 로드
# ------------------------------------------------------------------
def load_sentiment_dict(path: str) -> dict:
    """
    다양한 구분자(tab/space/comma)를 자동으로 인식해서
    {단어(어구): 극성점수} 형태의 dict 로 반환.
    - 단어에 공백이 포함된 어구(2-gram 이상)도 그대로 key 로 사용한다.
      (뒤에서 unigram / n-gram 매칭에 모두 사용)
    """
    senti_dict = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if "\t" in line:
                parts = line.split("\t")
            elif "," in line:
                parts = line.split(",")
            else:
                parts = line.rsplit(" ", 1)

            if len(parts) < 2:
                continue

            word = parts[0].strip()
            score_str = parts[-1].strip()
            try:
                score = float(score_str)
            except ValueError:
                continue

            if word:
                senti_dict[word] = score

    return senti_dict


# ------------------------------------------------------------------
# 2. 문장(리뷰) 감성 점수 계산
#    - 데이터가 이미 형태소 단위로 공백 분리되어 있으므로 토큰화는 str.split()
#    - unigram(단일 형태소) + bigram(형태소 2개 연속)까지 사전에서 찾아 매칭
# ------------------------------------------------------------------
def score_review(tokens: list, senti_dict: dict, max_ngram: int = 2):
    total_score = 0.0
    matched = []
    n = len(tokens)
    used = [False] * n

    for gram_len in range(max_ngram, 0, -1):
        for i in range(n - gram_len + 1):
            if any(used[i:i + gram_len]):
                continue
            phrase = " ".join(tokens[i:i + gram_len])
            if phrase in senti_dict:
                total_score += senti_dict[phrase]
                matched.append((phrase, senti_dict[phrase]))
                for j in range(i, i + gram_len):
                    used[j] = True

    return total_score, matched


def classify_score(score: float) -> str:
    if score > 0:
        return "긍정"
    elif score < 0:
        return "부정"
    else:
        return "중립"


# ------------------------------------------------------------------
# 3. 파일 목록 정리 (리스트 or glob 패턴 모두 지원)
# ------------------------------------------------------------------
def resolve_file_list(data_paths) -> list:
    """
    DATA_PATHS 가 문자열(glob 패턴)이든 리스트든 상관없이
    실제 존재하는 파일 경로 리스트로 변환.
    """
    if isinstance(data_paths, str):
        files = sorted(glob.glob(data_paths))
    else:
        files = []
        for p in data_paths:
            matched = glob.glob(p)
            files.extend(matched if matched else [p])

    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise FileNotFoundError(
            f"처리할 파일을 찾지 못했습니다. DATA_PATHS 설정을 확인하세요: {data_paths}"
        )
    return files


# ------------------------------------------------------------------
# 4. 파일 1개 처리
# ------------------------------------------------------------------
def process_one_file(file_path: str, senti_dict: dict, plots_dir: str) -> Optional[dict]:
    """
    파일 하나를 읽어 감성분석을 수행하고,
    - 파일명 접두어가 붙은 결과 csv / 그래프 3종을 저장
    - 요약 통계(dict)를 반환 (전체 비교용)
    """
    file_stem = os.path.splitext(os.path.basename(file_path))[0]
    print(f"\n{'=' * 60}\n[처리 중] {file_path}\n{'=' * 60}")

    df = pd.read_csv(file_path)
    if "cleaned_review" not in df.columns:
        print(f"  -> 'cleaned_review' 컬럼이 없어 건너뜁니다: {file_path}")
        return None

    df = df.dropna(subset=["cleaned_review"]).copy()
    df = df[df["cleaned_review"].str.strip() != ""]

    scores, labels, matched_words_list, matched_count = [], [], [], []
    for review in df["cleaned_review"]:
        tokens = review.split()
        score, matched = score_review(tokens, senti_dict, max_ngram=2)
        scores.append(score)
        labels.append(classify_score(score))
        matched_words_list.append(matched)
        matched_count.append(len(matched))

    df["lexicon_score"] = scores
    df["lexicon_sentiment"] = labels
    df["matched_word_count"] = matched_count

    label_counts = df["lexicon_sentiment"].value_counts()
    print("[감성 라벨 분포]")
    print(label_counts)

    coverage = (df["matched_word_count"] > 0).mean()
    print(f"사전 매칭 리뷰 비율: {coverage:.1%}")

    if "rating" in df.columns:
        print("[사전 기반 감성 라벨 별 평균 별점 (참고용)]")
        print(df.groupby("lexicon_sentiment")["rating"].mean())

    # ---------------- 시각화 (파일별로 접두어를 붙여 저장) ----------------
    order = ["긍정", "중립", "부정"]
    counts = label_counts.reindex(order).fillna(0)

    plt.figure(figsize=(6, 4.5))
    plt.bar(order, counts.values, color=["steelblue", "gray", "indianred"])
    plt.title(f"[{file_stem}] 사전 기반 감성분석 결과 분포", fontsize=11)
    plt.ylabel("리뷰 수")
    plt.tight_layout()
    plt.savefig(
        os.path.join(plots_dir, f"{file_stem}_lexicon_sentiment_distribution.png"),
        dpi=150, bbox_inches="tight",
    )
    plt.close()

    plt.figure(figsize=(7, 4.5))
    plt.hist(df["lexicon_score"], bins=20, color="steelblue", edgecolor="white")
    plt.axvline(0, color="black", linestyle="--", linewidth=1)
    plt.title(f"[{file_stem}] 리뷰별 감성 점수 분포", fontsize=11)
    plt.xlabel("감성 점수 (사전 기반 합산)")
    plt.ylabel("리뷰 수")
    plt.tight_layout()
    plt.savefig(
        os.path.join(plots_dir, f"{file_stem}_lexicon_score_histogram.png"),
        dpi=150, bbox_inches="tight",
    )
    plt.close()

    word_counter: Counter = Counter()
    for matched in matched_words_list:
        for word, _ in matched:
            word_counter[word] += 1

    if word_counter:
        top_words = word_counter.most_common(20)
        words, freqs = zip(*top_words)
        plt.figure(figsize=(8, 6))
        plt.barh(words[::-1], freqs[::-1], color="mediumseagreen")
        plt.title(f"[{file_stem}] 사전 매칭 감성 단어 TOP 20", fontsize=11)
        plt.xlabel("등장 리뷰 수")
        plt.tight_layout()
        plt.savefig(
            os.path.join(plots_dir, f"{file_stem}_lexicon_top_matched_words.png"),
            dpi=150, bbox_inches="tight",
        )
        plt.close()

    out_csv = os.path.join(plots_dir, f"{file_stem}_reviews_with_lexicon_sentiment.csv")
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"결과 저장: {out_csv}")

    # 전체 비교용 요약 통계
    n_total = len(df)
    summary = {
        "file": file_stem,
        "n_reviews": n_total,
        "n_positive": int(label_counts.get("긍정", 0)),
        "n_neutral": int(label_counts.get("중립", 0)),
        "n_negative": int(label_counts.get("부정", 0)),
        "positive_ratio": label_counts.get("긍정", 0) / n_total if n_total else 0,
        "negative_ratio": label_counts.get("부정", 0) / n_total if n_total else 0,
        "avg_lexicon_score": df["lexicon_score"].mean(),
        "dict_coverage": coverage,
    }
    return summary


# ------------------------------------------------------------------
# 5. 여러 파일 비교 시각화
# ------------------------------------------------------------------
def plot_cross_file_summary(summary_df: pd.DataFrame, plots_dir: str):
    if len(summary_df) < 2:
        return  # 파일이 1개뿐이면 비교 그래프 생략

    plt.figure(figsize=(max(6, len(summary_df) * 1.2), 5))
    x = np.arange(len(summary_df))
    pos = summary_df["n_positive"]
    neu = summary_df["n_neutral"]
    neg = summary_df["n_negative"]

    plt.bar(x, pos, label="긍정", color="steelblue")
    plt.bar(x, neu, bottom=pos, label="중립", color="gray")
    plt.bar(x, neg, bottom=pos + neu, label="부정", color="indianred")
    plt.xticks(x, summary_df["file"], rotation=30, ha="right")
    plt.ylabel("리뷰 수")
    plt.title("파일별 감성 분포 비교")
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        os.path.join(plots_dir, "cross_file_sentiment_comparison.png"),
        dpi=150, bbox_inches="tight",
    )
    plt.close()

    plt.figure(figsize=(max(6, len(summary_df) * 1.2), 5))
    plt.bar(summary_df["file"], summary_df["avg_lexicon_score"], color="mediumpurple")
    plt.axhline(0, color="black", linestyle="--", linewidth=1)
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("평균 감성 점수")
    plt.title("파일별 평균 감성 점수 비교")
    plt.tight_layout()
    plt.savefig(
        os.path.join(plots_dir, "cross_file_avg_score_comparison.png"),
        dpi=150, bbox_inches="tight",
    )
    plt.close()


# ------------------------------------------------------------------
# 6. 실행부
# ------------------------------------------------------------------
def main():
    senti_dict = load_sentiment_dict(DICT_PATH)
    print(f"사전 단어(어구) 수: {len(senti_dict)}")

    files = resolve_file_list(DATA_PATHS)
    print(f"처리 대상 파일 {len(files)}개: {files}")

    summaries = []
    for file_path in files:
        summary = process_one_file(file_path, senti_dict, PLOTS_DIR)
        if summary is not None:
            summaries.append(summary)

    if not summaries:
        print("\n처리된 파일이 없습니다.")
        return

    summary_df = pd.DataFrame(summaries)
    summary_csv = os.path.join(PLOTS_DIR, "cross_file_summary.csv")
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    print(f"\n{'=' * 60}\n[전체 파일 요약]\n{'=' * 60}")
    print(summary_df)
    print(f"\n요약 결과 저장: {summary_csv}")

    plot_cross_file_summary(summary_df, PLOTS_DIR)


if __name__ == "__main__":
    main()