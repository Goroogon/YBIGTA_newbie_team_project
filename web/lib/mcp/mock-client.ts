/**
 * 로컬 개발/테스트용 Mock MCP 클라이언트.
 *
 * 팀원 B가 실제 MCP 서버 주소(MCP_SERVER_URL)와 토큰(MCP_AUTH_TOKEN)을 넘겨주기 전까지,
 * Agent 로직(app/api/chat, lib/llm.ts)과 채팅 UI를 실제 데이터 흐름과 동일한 방식으로
 * 미리 개발/검증할 수 있도록 real-client.ts와 동일한 인터페이스(McpClient)로 구현했습니다.
 *
 * 데이터는 mcp_server/models/review.py의 Review 스키마(site/review_date/rating/content/
 * cleaned_review/day_of_week/tf_idf_mean_score/collected_at)를 그대로 따라 만든 가짜 리뷰입니다.
 *
 * 나중에 실제 서버가 준비되면 .env에 MCP_SERVER_URL / MCP_AUTH_TOKEN만 채우면
 * lib/mcp/index.ts가 자동으로 real-client.ts로 전환하므로, 이 파일은 그대로 남겨둬도 됩니다.
 */
import {
  AggregateDataArgs,
  AggregateDataResult,
  ALLOWED_SITES,
  GetAvailableSitesResult,
  GetLatestDataArgs,
  GetLatestDataResult,
  McpClient,
  ReviewItem,
  SearchDataArgs,
  SearchDataResult,
} from "./types";

const CONTENT_TEMPLATES: Array<{ text: string; cleaned: string; rating: number }> = [
  { text: "배우들 연기가 정말 인상 깊었어요. 특히 주연 배우의 표정 연기가 최고였습니다.", cleaned: "연기 인상 주연 배우 표정 최고", rating: 5 },
  { text: "스토리 전개가 좀 늘어지는 느낌이라 중반부는 지루했어요.", cleaned: "스토리 전개 늘어지 중반부 지루", rating: 3 },
  { text: "연출이 감동적이었고 눈물이 났습니다. 강력 추천!", cleaned: "연출 감동 눈물 추천", rating: 5 },
  { text: "기대했던 것보다 아쉬운 결말이었습니다. 그래도 배우 연기는 좋았어요.", cleaned: "기대 아쉬운 결말 배우 연기", rating: 3 },
  { text: "역사적 소재를 다루는 방식이 흥미로웠고 몰입감이 높았습니다.", cleaned: "역사 소재 방식 흥미 몰입감", rating: 4 },
  { text: "그냥 그랬어요. 시간 때우기용으로는 괜찮습니다.", cleaned: "그냥 시간 때우기용 괜찮", rating: 2 },
  { text: "최고의 영화입니다. 연기, 연출, 스토리 다 완벽했어요.", cleaned: "최고 영화 연기 연출 스토리 완벽", rating: 5 },
  { text: "억지스러운 전개가 몰입을 방해했습니다.", cleaned: "억지 전개 몰입 방해", rating: 2 },
  { text: "감정선이 잘 살아있어서 계속 눈물이 났어요.", cleaned: "감정선 눈물", rating: 5 },
  { text: "배우 연기는 훌륭했지만 스토리가 다소 예측 가능했습니다.", cleaned: "배우 연기 훌륭 스토리 예측", rating: 3 },
];

const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function seededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

function buildMockReviews(): ReviewItem[] {
  const rand = seededRandom(42);
  const now = new Date();
  const reviews: ReviewItem[] = [];
  let id = 1;

  for (const site of ALLOWED_SITES) {
    // 사이트마다 45일 동안 하루 1~4건씩 생성
    for (let daysAgo = 45; daysAgo >= 0; daysAgo--) {
      const countToday = 1 + Math.floor(rand() * 4);
      for (let i = 0; i < countToday; i++) {
        const template = CONTENT_TEMPLATES[Math.floor(rand() * CONTENT_TEMPLATES.length)];
        const reviewDate = new Date(now);
        reviewDate.setDate(reviewDate.getDate() - daysAgo);

        const collectedAt = new Date(reviewDate);
        collectedAt.setHours(collectedAt.getHours() + Math.floor(rand() * 6));

        const ratingJitter = (rand() - 0.5) * 1.2;
        const rating = Math.max(0.5, Math.min(5, Math.round((template.rating + ratingJitter) * 2) / 2));

        reviews.push({
          id: id++,
          site,
          review_date: reviewDate.toISOString().slice(0, 10),
          rating,
          content: template.text,
          cleaned_review: template.cleaned,
          day_of_week: DAY_NAMES[reviewDate.getDay()],
          tf_idf_mean_score: Math.round(rand() * 0.3 * 1000) / 1000,
          collected_at: collectedAt.toISOString(),
        });
      }
    }
  }
  return reviews;
}

// 모듈 로드 시 한 번만 생성해서 재사용 (매 요청마다 랜덤 데이터가 바뀌면 디버깅이 어려워짐)
const MOCK_REVIEWS = buildMockReviews();

function validateSite(site: string | undefined) {
  if (site && !ALLOWED_SITES.includes(site as (typeof ALLOWED_SITES)[number])) {
    throw new Error(`허용되지 않는 site입니다. 가능한 값: ${JSON.stringify(ALLOWED_SITES)}`);
  }
}

function validateDate(label: string, value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new Error(`${label}는 YYYY-MM-DD 형식이어야 합니다.`);
  }
}

export function createMockClient(): McpClient {
  return {
    kind: "mock",

    async searchData(args: SearchDataArgs): Promise<SearchDataResult> {
      const { keyword, start_date, end_date, site, limit = 20, offset = 0 } = args;
      if (!keyword || keyword.length > 100) {
        throw new Error("keyword는 1~100자 사이여야 합니다.");
      }
      validateDate("start_date", start_date);
      validateDate("end_date", end_date);
      if (start_date > end_date) {
        throw new Error("start_date는 end_date보다 이전이어야 합니다.");
      }
      validateSite(site);
      const boundedLimit = Math.min(Math.max(limit, 1), 100);

      const filtered = MOCK_REVIEWS.filter(
        (r) =>
          r.content.includes(keyword) &&
          r.review_date! >= start_date &&
          r.review_date! <= end_date &&
          (!site || r.site === site)
      ).sort((a, b) => (b.review_date! > a.review_date! ? 1 : -1));

      const page = filtered.slice(offset, offset + boundedLimit);
      return { count: page.length, results: page };
    },

    async getLatestData(args: GetLatestDataArgs): Promise<GetLatestDataResult> {
      const { site, limit = 10 } = args;
      validateSite(site);
      const boundedLimit = Math.min(Math.max(limit, 1), 100);

      const filtered = MOCK_REVIEWS.filter((r) => !site || r.site === site).sort((a, b) =>
        b.collected_at! > a.collected_at! ? 1 : -1
      );
      const page = filtered.slice(0, boundedLimit);
      return { count: page.length, results: page };
    },

    async aggregateData(args: AggregateDataArgs): Promise<AggregateDataResult> {
      const { site, start_date, end_date } = args;
      validateSite(site);
      if (!ALLOWED_SITES.includes(site as (typeof ALLOWED_SITES)[number])) {
        throw new Error(`허용되지 않는 site입니다. 가능한 값: ${JSON.stringify(ALLOWED_SITES)}`);
      }
      validateDate("start_date", start_date);
      validateDate("end_date", end_date);
      if (start_date > end_date) {
        throw new Error("start_date는 end_date보다 이전이어야 합니다.");
      }

      const filtered = MOCK_REVIEWS.filter(
        (r) => r.site === site && r.review_date! >= start_date && r.review_date! <= end_date
      );
      const avg =
        filtered.length > 0 ? filtered.reduce((sum, r) => sum + r.rating, 0) / filtered.length : null;

      return {
        site,
        period: { start: start_date, end: end_date },
        avg_rating: avg !== null ? Math.round(avg * 100) / 100 : null,
        review_count: filtered.length,
      };
    },

    async getAvailableSites(): Promise<GetAvailableSitesResult> {
      return { sites: [...ALLOWED_SITES] };
    },
  };
}
