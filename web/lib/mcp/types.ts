/**
 * MCP 서버(팀원 B 파트)가 제공하는 4개 Tool과 동일한 계약(contract)을 TypeScript 타입으로 정의.
 *
 * 실제 MCP 서버 코드(mcp_server/tools/*.py, mcp_server/services/*.py)를 기준으로 맞췄습니다.
 * - search_data(keyword, start_date, end_date, site?, limit?, offset?)
 * - get_latest_data(site?, limit?)
 * - aggregate_data(site, start_date, end_date)
 * - get_available_sites()
 *
 * real-client.ts(실제 MCP 서버 연결)와 mock-client.ts(로컬 개발용 가짜 데이터)가
 * 모두 이 McpClient 인터페이스를 구현하므로, 나중에 실제 MCP 서버 주소/토큰만
 * 채워 넣으면 코드 변경 없이 real-client로 전환됩니다. (lib/mcp/index.ts 참고)
 */

export interface ReviewItem {
  id: number;
  site: string;
  review_date: string | null;
  rating: number;
  content: string;
  cleaned_review: string | null;
  day_of_week: string | null;
  tf_idf_mean_score: number | null;
  collected_at: string | null;
}

export interface SearchDataArgs {
  keyword: string;
  start_date: string;
  end_date: string;
  site?: string;
  limit?: number;
  offset?: number;
}

export interface GetLatestDataArgs {
  site?: string;
  limit?: number;
}

export interface AggregateDataArgs {
  site: string;
  start_date: string;
  end_date: string;
}

export interface SearchDataResult {
  count: number;
  results: ReviewItem[];
}

export interface GetLatestDataResult {
  count: number;
  results: ReviewItem[];
}

export interface AggregateDataResult {
  site: string;
  period: { start: string; end: string };
  avg_rating: number | null;
  review_count: number;
}

export interface GetAvailableSitesResult {
  sites: string[];
}

export interface McpClient {
  /** 어떤 MCP 클라이언트가 실제로 쓰이고 있는지 UI/로그에 표시하기 위한 식별자 */
  readonly kind: "real" | "mock";
  searchData(args: SearchDataArgs): Promise<SearchDataResult>;
  getLatestData(args: GetLatestDataArgs): Promise<GetLatestDataResult>;
  aggregateData(args: AggregateDataArgs): Promise<AggregateDataResult>;
  getAvailableSites(): Promise<GetAvailableSitesResult>;
}

export const ALLOWED_SITES = ["megabox", "naver", "kinolights"] as const;
