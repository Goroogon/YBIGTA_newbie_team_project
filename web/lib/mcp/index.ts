/**
 * MCP 클라이언트 진입점.
 *
 * MCP_SERVER_URL / MCP_AUTH_TOKEN 이 .env에 설정되어 있으면 실제 MCP 서버(팀원 B 배포본)에 붙고,
 * 없으면 자동으로 mock 클라이언트로 동작합니다.
 * → 팀원 B에게 값을 넘겨받으면 .env만 채우면 되고, 코드/브랜치 변경이 필요 없습니다.
 *
 * 서버 컴포넌트/Route Handler에서만 import 하세요 (클라이언트 컴포넌트에서 import 금지).
 */
import "server-only";
import { McpClient } from "./types";
import { createMockClient } from "./mock-client";
import { createRealClient } from "./real-client";

let cachedClient: McpClient | null = null;

export function getMcpClient(): McpClient {
  if (cachedClient) return cachedClient;

  const baseUrl = process.env.MCP_SERVER_URL?.trim();
  const token = process.env.MCP_AUTH_TOKEN?.trim();

  if (baseUrl && token) {
    cachedClient = createRealClient({ baseUrl, token });
    console.log(`[mcp] MCP_SERVER_URL이 설정되어 있어 실제 MCP 서버(${baseUrl})에 연결합니다.`);
  } else {
    cachedClient = createMockClient();
    console.warn(
      "[mcp] MCP_SERVER_URL / MCP_AUTH_TOKEN이 설정되지 않아 Mock MCP 클라이언트를 사용합니다. " +
        "(팀원 B에게 값을 받으면 .env에 채워주세요)"
    );
  }
  return cachedClient;
}

export type { McpClient } from "./types";
