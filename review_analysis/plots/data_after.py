"""
kinolights / megabox / naver 리뷰 데이터 검증 스크립트

목적:
  1) 각 파일에 결측치가 있는지 확인 (500개 수집했다면 500행 다 채워져있는지)
  2) 3개 파일의 평점 분포를 시각화 (평점 척도가 서로 다르다는 것을 확인)

전처리 전/후를 비교하고 싶으면, 아래 STAGE와 파일 경로만 바꿔서
다시 실행하면 돼. (전처리 전 한 번, 전처리 후 한 번 실행 → 결과 파일명이
STAGE에 따라 달라져서 둘 다 남아있음)
"""

import os
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd

# ----------------------------------------------------------------------
# 설정 - 여기만 상황에 맞게 바꾸면 됨
# ----------------------------------------------------------------------
STAGE = "preprocessed"  

FILES = {
    "kinolights": "database/reviews_kinolights.csv",
    "megabox": "database/reviews_megabox.csv",
    "naver": "database/reviews_naver.csv",
}

EXPECTED_MIN_ROWS = 500  # 과제 최소조건

OUTPUT_DIR = "./check_outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 한글 폰트 설정
_CANDIDATE_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic"]
_available = {f.name for f in fm.fontManager.ttflist}
for _font in _CANDIDATE_FONTS:
    if _font in _available:
        plt.rcParams["font.family"] = _font
        break
plt.rcParams["axes.unicode_minus"] = False

COLORS = {"kinolights": "#4263eb", "megabox": "#f03e3e", "naver": "#0ca678"}


# ----------------------------------------------------------------------
# 1) 결측치 확인
# ----------------------------------------------------------------------
def check_missing_values(dfs: dict) -> pd.DataFrame:
    rows = []
    for site, df in dfs.items():
        n_rows = len(df)
        missing_per_col = df.isnull().sum()
        total_missing = missing_per_col.sum()
        rows.append(
            {
                "site": site,
                "행 개수": n_rows,
                "500개 이상 충족": "충족" if n_rows >= EXPECTED_MIN_ROWS else "미달",
                "rating 결측": missing_per_col.get("rating", 0),
                "date 결측": missing_per_col.get("date", 0),
                "content 결측": missing_per_col.get("content", 0),
                "총 결측치": total_missing,
                "결측치 없는 완전한 행": n_rows - df.isnull().any(axis=1).sum(),
            }
        )
    result = pd.DataFrame(rows).set_index("site")

    print("=" * 70)
    print(f"[{STAGE}] 결측치 확인 결과")
    print("=" * 70)
    print(result.to_string())
    print()
    for site in dfs:
        total_missing = result.loc[site, "총 결측치"]
        if total_missing == 0:
            print(f"✔ {site}: 결측치 없음 — {result.loc[site, '행 개수']}개 행 모두 완전하게 채워져 있음")
        else:
            print(f"✘ {site}: 결측치 {total_missing}건 발견 (아래 표에서 어느 컬럼인지 확인)")
    print()

    result.to_csv(
        os.path.join(OUTPUT_DIR, f"missing_check_{STAGE}.csv"), encoding="utf-8-sig"
    )
    return result


def plot_missing_values(summary: pd.DataFrame):
    """결측치 확인 결과를 이미지로 저장한다.
    왼쪽: 사이트별 컬럼별 결측치 개수 (막대그래프, 다 0이면 막대가 안 보이는 것으로
          '결측치 없음'을 시각적으로 보여줌)
    오른쪽: 사이트별 행 개수 (500개 기준선과 함께, 최소조건 충족 여부 확인용)
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 왼쪽: 컬럼별 결측치 개수
    cols = ["rating 결측", "date 결측", "content 결측"]
    summary[cols].plot(kind="bar", ax=axes[0])
    axes[0].set_title(f"[{STAGE}] 사이트별 컬럼별 결측치 개수")
    axes[0].set_ylabel("결측치 개수")
    axes[0].set_xticklabels(summary.index, rotation=0)
    axes[0].set_ylim(bottom=0)
    # 결측치가 하나도 없으면 눈에 보이게 안내 문구 표시
    if summary[cols].sum().sum() == 0:
        axes[0].text(
            0.5, 0.5, "결측치 없음",
            transform=axes[0].transAxes, ha="center", va="center",
            fontsize=16, color="gray", alpha=0.6,
        )

    # 오른쪽: 행 개수 vs 최소조건(500)
    bars = axes[1].bar(
        summary.index, summary["행 개수"],
        color=[COLORS[s] for s in summary.index],
    )
    axes[1].axhline(EXPECTED_MIN_ROWS, color="red", linestyle="--", label=f"최소조건 {EXPECTED_MIN_ROWS}개")
    for bar, n in zip(bars, summary["행 개수"]):
        axes[1].text(bar.get_x() + bar.get_width() / 2, n + 5, str(n), ha="center")
    axes[1].set_title(f"[{STAGE}] 사이트별 행 개수 (최소조건 {EXPECTED_MIN_ROWS}개 기준)")
    axes[1].set_ylabel("행 개수")
    axes[1].legend()

    fig.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, f"missing_check_{STAGE}.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"결측치 확인 그래프 저장: {out_path}")


# ----------------------------------------------------------------------
# 2) 평점 분포 시각화
# ----------------------------------------------------------------------
def plot_rating_distribution(dfs: dict):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, (site, df) in zip(axes, dfs.items()):
        rating_min, rating_max = df["rating"].min(), df["rating"].max()
        ax.hist(df["rating"], bins=20, color=COLORS[site], edgecolor="white")
        ax.set_title(f"{site}\n(관측된 범위: {rating_min} ~ {rating_max})")
        ax.set_xlabel("rating")
        ax.set_ylabel("리뷰 개수")
    fig.suptitle(f"[{STAGE}] 사이트별 평점 분포 (원본 척도 그대로)", fontsize=13)
    fig.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, f"rating_distribution_{STAGE}.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"평점 분포 그래프 저장: {out_path}")

    # 척도 비교를 한눈에 보여주는 요약도 같이 출력
    print()
    print("-" * 40)
    print("평점 척도 비교")
    print("-" * 40)
    for site, df in dfs.items():
        print(f"{site}: {df['rating'].min()} ~ {df['rating'].max()} 척도")


# ----------------------------------------------------------------------
# 실행
# ----------------------------------------------------------------------
def main():
    dfs = {site: pd.read_csv(path, encoding="utf-8-sig") for site, path in FILES.items()}

    summary = check_missing_values(dfs)
    plot_missing_values(summary)
    plot_rating_distribution(dfs)


if __name__ == "__main__":
    main()