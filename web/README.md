# Data Analysis Agent (팀원 C 파트 — 권준범)

`[과제] AI Agent` 명세의 7~10번(Vercel + Next.js Data Analysis Agent) 담당 부분입니다.

## 현재 상태

MCP 서버(팀원 B) 배포 주소/인증 토큰을 아직 전달받기 전이라, **먼저 만들 수 있는 부분을 전부 완성**해두고
값만 받으면 바로 이어붙일 수 있도록 준비했습니다.

- `.env`에 `MCP_SERVER_URL` / `MCP_AUTH_TOKEN`이 **없으면** → `lib/mcp/mock-client.ts`가 자동으로 쓰입니다.
  실제 MCP 서버(`mcp_server/`)의 Tool 계약(이름/파라미터/검증 규칙)과 동일하게 동작하는 가짜 리뷰 데이터로,
  Agent 로직·UI를 지금 바로 개발/테스트할 수 있습니다.
- `.env`에 두 값이 **채워지면** → `lib/mcp/real-client.ts`(실제 MCP 서버에 SSE로 연결)가 자동으로 대신 쓰입니다.
  **코드 수정이나 브랜치 변경 없이** `.env`만 채우면 전환됩니다. (`lib/mcp/index.ts` 참고)

## 구조

```
web/
├── app/
│   ├── page.tsx           # 채팅 UI 페이지
│   ├── layout.tsx
│   └── api/chat/route.ts  # Route Handler (Server Side) — LLM 호출, MCP Tool 인증 전부 여기서만 처리
├── components/
│   └── Chat.tsx            # "use client" — 입력/표시만 담당, API Key/Token 없음
├── lib/
│   ├── llm.ts               # Anthropic tool use로 MCP Tool 선택/호출하는 Agent 루프
│   └── mcp/
│       ├── types.ts         # MCP 서버 Tool 계약과 동일한 TypeScript 타입
│       ├── index.ts         # real/mock 자동 선택
│       ├── real-client.ts   # 실제 MCP 서버(SSE + Bearer Token)에 연결
│       └── mock-client.ts   # 로컬 개발용 가짜 데이터 (real-client와 동일 인터페이스)
└── .env.example
```

## 흐름 (과제 8번 요구사항)

```
사용자 질문 → Chat.tsx → POST /api/chat → runAgent()
  → Anthropic Claude가 필요한 MCP Tool 선택 (search_data / get_latest_data / aggregate_data / get_available_sites)
  → lib/mcp의 클라이언트(real 또는 mock)로 Tool 호출 → 결과를 Claude에게 다시 전달
  → Claude가 최종 분석 답변 생성 → 사용자에게 응답 (호출된 Tool 로그도 함께 반환)
```

LLM이 직접 SQL을 만들거나 DB/MCP 서버에 접근하는 경로는 없습니다 — 항상 `lib/mcp`를 통해서만 접근합니다.

## 보안 (과제 9번 요구사항)

- `ANTHROPIC_API_KEY`, `MCP_AUTH_TOKEN`, `MCP_SERVER_URL`은 전부 `app/api/chat/route.ts`, `lib/*`에서만 사용되고 `"use client"` 컴포넌트로 전달되지 않습니다.
- `lib/mcp/index.ts`, `lib/llm.ts`에 `import "server-only"`를 넣어, 실수로 클라이언트 컴포넌트에서 import하면 **빌드 타임에 에러**가 나도록 강제했습니다.
- 환경변수 이름에 `NEXT_PUBLIC_`을 쓰지 않았습니다.
- 브라우저는 `/api/chat`만 호출하고, MCP 서버를 직접 호출하지 않습니다.

## 로컬 실행

```bash
cd web
npm install
cp .env.example .env.local
# .env.local에 최소 ANTHROPIC_API_KEY만 채우면 Mock 데이터로 바로 동작 확인 가능
npm run dev
```

`http://localhost:3000` 접속 → 예시 질문 버튼 클릭 또는 직접 입력.
답변 아래 "MCP Tool 호출 N건"을 펼치면 어떤 Tool이 어떤 인자로 호출됐는지, real/mock 중 무엇을 썼는지 확인할 수 있습니다.

> `.env.local`은 `.gitignore`(`.env*`)에 의해 항상 커밋에서 제외됩니다. (2026-08-13 기준 팀원 B에게 받은 실제 MCP_SERVER_URL/MCP_AUTH_TOKEN이 이미 `web/.env.local`에 채워져 있습니다 — 없다면 `web/env.local.txt`를 `.env.local`로 이름만 바꾸면 됩니다. ANTHROPIC_API_KEY만 본인 걸로 채워주세요.)

## 팀원 B에게 받으면 할 일

1. `.env.local`의 `MCP_SERVER_URL`, `MCP_AUTH_TOKEN`을 실제 값으로 채우기 (완료됨)
2. `npm run dev`로 재시작 후 콘솔에 `[mcp] MCP_SERVER_URL이 설정되어 있어 실제 MCP 서버(...)에 연결합니다.` 로그 확인
3. "현재 가장 최근 데이터는 뭐야?" 같은 질문으로 실제 DB 데이터가 돌아오는지 확인 (`aws/agent_query.png`, `aws/agent_analysis.png` 캡처)
4. 문제가 있다면 `mcp_server/nginx.conf`의 Bearer Token 플레이스홀더 치환 여부, `mcp_server/server.py`의 SSE 엔드포인트 경로(`/sse`)를 팀원 B와 함께 확인

## Vercel 배포 시

- 프로젝트 루트를 `web/`로 설정 (Root Directory)
- Environment Variables에 `.env.example`의 키들을 등록 (Vercel 대시보드에만 입력하고 절대 커밋하지 않기)
