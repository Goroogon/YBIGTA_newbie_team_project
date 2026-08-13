/**
 * 실제 MCP 서버(팀원 B가 EC2에 배포한 mcp_server/)에 연결하는 클라이언트.
 *
 * mcp_server/server.py가 mcp==1.2.0의 FastMCP를 SSE transport로 띄우고 있고,
 * mcp_server/nginx.conf가 모든 요청에 `Authorization: Bearer <MCP_AUTH_TOKEN>` 헤더를
 * 요구하므로, SSE 연결(GET)과 메시지 전송(POST) 양쪽 모두에 헤더를 실어야 합니다.
 *
 * 주의: 과제 명세(9번 항목)에 따라 이 클라이언트는 반드시 Next.js의 Server Side
 * (app/api/chat/route.ts 같은 Route Handler)에서만 생성/호출되어야 하며,
 * "use client" 컴포넌트나 브라우저에서 직접 import하면 안 됩니다.
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import {
  AggregateDataArgs,
  AggregateDataResult,
  GetAvailableSitesResult,
  GetLatestDataArgs,
  GetLatestDataResult,
  McpClient,
  SearchDataArgs,
  SearchDataResult,
} from "./types";

interface RealClientOptions {
  /** 예: https://mcp.example.com 또는 http://<EC2 IP> (nginx가 80/443에서 리버스 프록시) */
  baseUrl: string;
  /** MCP_AUTH_TOKEN 값. Authorization: Bearer <token> 형태로 전송됨 */
  token: string;
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

/**
 * MCP Tool 호출 결과(content blocks)를 JS 객체로 변환.
 * FastMCP(구버전)는 dict를 반환하면 보통 첫 번째 text content에 JSON 문자열로 직렬화해서 내려줌.
 */
function parseToolResult(result: unknown): unknown {
  const content = (result as { content?: Array<{ type: string; text?: string }> })?.content;
  if (Array.isArray(content) && content.length > 0) {
    const textBlock = content.find((c) => c.type === "text" && typeof c.text === "string");
    if (textBlock?.text) {
      try {
        return JSON.parse(textBlock.text);
      } catch {
        return textBlock.text;
      }
    }
  }
  return result;
}

async function withConnection<T>(opts: RealClientOptions, fn: (client: Client) => Promise<T>): Promise<T> {
  // FastMCP(mcp==1.2.0) SSE transport 기본 엔드포인트는 /sse 이며,
  // 서버가 SSE 핸드셰이크 중 'endpoint' 이벤트로 실제 메시지 POST 경로를 알려준다.
  const sseUrl = new URL("/sse", opts.baseUrl);

  const transport = new SSEClientTransport(sseUrl, {
    // 최초 SSE(GET) 연결에도 Authorization 헤더가 필요하므로 커스텀 fetch로 헤더를 주입
    eventSourceInit: {
      fetch: (input, init) =>
        fetch(input, {
          ...init,
          headers: { ...(init?.headers ?? {}), ...authHeaders(opts.token) },
        }),
    },
    // 이후 메시지 POST 요청에 실어 보낼 헤더
    requestInit: {
      headers: authHeaders(opts.token),
    },
  });

  const client = new Client({ name: "ybigta-data-analysis-agent", version: "1.0.0" }, { capabilities: {} });

  await client.connect(transport);
  try {
    return await fn(client);
  } finally {
    await client.close();
  }
}

export function createRealClient(opts: RealClientOptions): McpClient {
  return {
    kind: "real",

    async searchData(args: SearchDataArgs): Promise<SearchDataResult> {
      return withConnection(opts, async (client) => {
        const result = await client.callTool({ name: "search_data", arguments: { ...args } });
        return parseToolResult(result) as SearchDataResult;
      });
    },

    async getLatestData(args: GetLatestDataArgs): Promise<GetLatestDataResult> {
      return withConnection(opts, async (client) => {
        const result = await client.callTool({ name: "get_latest_data", arguments: { ...args } });
        return parseToolResult(result) as GetLatestDataResult;
      });
    },

    async aggregateData(args: AggregateDataArgs): Promise<AggregateDataResult> {
      return withConnection(opts, async (client) => {
        const result = await client.callTool({ name: "aggregate_data", arguments: { ...args } });
        return parseToolResult(result) as AggregateDataResult;
      });
    },

    async getAvailableSites(): Promise<GetAvailableSitesResult> {
      return withConnection(opts, async (client) => {
        const result = await client.callTool({ name: "get_available_sites", arguments: {} });
        return parseToolResult(result) as GetAvailableSitesResult;
      });
    },
  };
}
