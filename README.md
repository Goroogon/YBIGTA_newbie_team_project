# YBIGTA Newbie Team Project — AI Agent

데이터 수집 → DB 자동 갱신 → MCP를 통한 데이터 조회 → Agent를 통한 분석까지
하나의 서비스로 연결한 프로젝트입니다.

---

## Architecture

```
External Data (megabox 리뷰)
        │ 자동 수집
        ▼
AWS Collector (EC2, cron)
        │ 데이터 저장
        ▼
┌─────────────────────────────────────────┐
│ AWS VPC                                  │
│                                           │
│  Public Subnet                           │
│  ┌─────────────────────────────────┐     │
│  │ MCP Server (EC2)                 │     │
│  │  Nginx(80/443, Bearer 인증)       │     │
│  │   └─ MCP App(:8000, 내부 전용)    │     │
│  └───────────────┬───────────────────┘     │
│                  │ Private Network         │
│  Private Subnet  │                         │
│  ┌───────────────▼─────────────────┐     │
│  │ RDS (coin_db / reviews)          │     │
│  │  Public Access: OFF               │     │
│  └───────────────────────────────────┘     │
└─────────────────────────────────────────┘
                  ▲
                  │ MCP Tool Call (SSE)
                  │
        ┌─────────┴─────────┐
        │ Vercel / Next.js   │
        │ Data Agent          │
        └─────────┬─────────┘
                  ▼
                사용자
```

> TODO: 위 텍스트 다이어그램을 실제 이미지(draw.io, excalidraw 등)로 만들어서
> `aws/architecture.png`로 첨부해주세요.

---

## Data Pipeline

- 어떤 데이터를 수집하는가: Megabox 영화 리뷰 데이터 (별점, 리뷰 내용, 작성일, 전처리된 리뷰, 요일, TF-IDF 평균 점수)
- 어떤 주기로 갱신되는가: 10분 간격 (사전에 수집·전처리된 리뷰 데이터를 배치 단위(20건씩)로 순환하며 DB에 반영)
- 어떤 AWS 기능을 사용했는가 (EC2 cron / EventBridge 등): EC2(collector 인스턴스, Public Subnet) + cron(주기적 자동 실행), RDS MySQL(Private Subnet, Public Access OFF), VPC(Public/Private Subnet 분리, 2개 가용 영역)
- DB Schema:

```sql
-- reviews 테이블
CREATE TABLE reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(50) NOT NULL,
    review_date DATE NOT NULL,
    rating FLOAT NOT NULL,
    content TEXT NOT NULL,
    cleaned_review TEXT,
    day_of_week VARCHAR(10),
    tf_idf_mean_score FLOAT,
    collected_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_site (site),
    INDEX idx_collected_at (collected_at)
);
```

캡처: `aws/data_update.png` (서로 다른 시간에 데이터가 갱신된 것을 보여주는 캡처)

---

## MCP

### 어떤 Tool이 존재하는가 / 각 Tool은 무엇을 하는가

| Tool | 설명 | 파라미터 |
|---|---|---|
| `search_data` | 키워드/기간으로 리뷰 검색 | `keyword`, `start_date`, `end_date`, `limit` |
| `get_latest_data` | 가장 최근에 수집된 리뷰 데이터 조회 | `site` (megabox/naver/kinolights, 생략 시 전체), `limit` (기본 10, 최대 10~100) |
| `get_available_sites` | 조회 가능한 사이트 목록 확인 | 없음 |
| `aggregate_data` | 리뷰 데이터 집계/통계 (평균 평점 `avg_rating`, 리뷰 수 `review_count` 반환) | `site` (필수, megabox/naver/kinolights), `start_date` (필수, YYYY-MM-DD), `end_date` (필수, YYYY-MM-DD) |

### 왜 이러한 Tool 구조를 선택했는가

- Agent가 DB 전체를 가져가 LLM에게 분석을 맡기지 않고, **필요한 데이터만 MCP Tool로 선택적으로 조회**하도록 설계했습니다.
- Raw SQL을 그대로 실행하는 `execute_sql` 형태의 Tool은 만들지 않았습니다. 대신 각 Tool마다 허용 가능한 파라미터(keyword, date range, limit 등)를 명시적으로 제한하여 대량 조회·예상치 못한 쿼리를 방지했습니다.
- 조회 결과에는 `limit` 상한(기본 10, 최대 10~100)을 적용해 과도한 데이터 반환을 막았습니다.

### 코드 구조 (MCP Tool → Service → Repository)

```
mcp_server/
├── server.py          # FastMCP 인스턴스 생성 및 Tool 등록
├── tools/              # MCP Tool 정의 (search, latest, aggregation)
├── services/            # 비즈니스 로직
├── repositories/         # DB 접근 계층 (parameterized query)
├── Dockerfile
├── requirements.txt
└── .env.example
```

MCP Tool이 DB Connection과 SQL을 직접 다루지 않고 Service → Repository 계층을 거치도록 분리했습니다. 이렇게 하면 나중에 검색 백엔드를 MySQL에서 Elasticsearch/OpenSearch 등으로 교체하더라도 MCP Tool 자체는 그대로 두고 Repository 구현체만 교체할 수 있습니다.

### 새로운 데이터나 Tool을 추가하려면 어떻게 하면 되는가

1. `repositories/`에 새 데이터 소스에 대한 Repository 클래스 추가
2. `services/`에 해당 데이터를 다루는 Service 함수 추가
3. `tools/`에 새 Tool 함수를 만들고 `server.py`에서 `register()` 호출로 등록

---

## Security

### 왜 DB를 Private Subnet에 두었는가

RDS를 외부 인터넷에서 직접 접근하지 못하도록 하기 위함입니다. DB는 MCP 서버를 통해서만 조회되어야 하고, 그 외 경로(Vercel, 외부 클라이언트 등)에서 직접 접근할 수 없어야 하기 때문에 Private Subnet에 배치하고 `Publicly Accessible: No`로 설정했습니다.

### RDS Security Group은 어떻게 설정했는가

RDS 인바운드 규칙은 `0.0.0.0/0` 형태로 열지 않고, MCP 서버가 속한 보안그룹(`mcp-sg`)에서만 3306 포트로 접근 가능하도록 제한했습니다.

```
RDS Security Group Inbound
MySQL 3306   Source: mcp-sg
```

또한 DB 계정을 역할별로 분리했습니다:
- `mcp_user`: **read-only(SELECT)** 권한만 부여 — MCP 서버는 데이터 조회만 하면 되므로
- collector 쪽 계정은 별도로 INSERT/UPDATE 권한을 가짐 (A 담당 EC2)

캡처: `aws/rds_private.png`, `aws/security_group.png`

### MCP의 내부 API Port를 어떻게 보호했는가

MCP 애플리케이션은 내부적으로 8000번 포트에서 실행되지만, 이 포트를 인터넷에 직접 노출하지 않았습니다.

```
Internet → Nginx(80) → MCP(127.0.0.1:8000, 내부 전용)
```

- MCP 서버 컨테이너를 `docker run -p 127.0.0.1:8000:8000 ...` 형태로 실행하여, EC2 **내부에서만** 8000번 포트에 접근 가능하도록 바인딩했습니다.
- EC2의 mcp-sg 보안그룹 인바운드는 80/443(HTTP/HTTPS)과 22(SSH, 내 IP 한정)만 허용하고, 8000/3306 등 애플리케이션·DB 포트는 전혀 열지 않았습니다.

### MCP 인증은 어떻게 구현했는가

`mcp` 라이브러리(1.2.0) 버전이 ASGI 앱을 직접 노출하지 않아 애플리케이션 레벨 미들웨어 인증이 불가능했기 때문에, **Nginx 리버스 프록시 단에서 Bearer Token 인증**을 처리하도록 구현했습니다.

```nginx
map_hash_bucket_size 128;

map $http_authorization $auth_ok {
    "Bearer <MCP_AUTH_TOKEN>" 1;
    default 0;
}

server {
    listen 80;
    server_name _;

    location / {
        if ($auth_ok = 0) {
            return 401;
        }
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```

- 토큰 없이 요청 시 **401** 응답 확인 완료
- 유효한 토큰(`Authorization: Bearer <MCP_AUTH_TOKEN>`)으로 요청 시 정상 응답 확인 완료
- CORS 설정과는 별개로 서버 자체(Nginx)에서 인증을 검사하도록 구현하여, "CORS만으로는 인증이 아니다"라는 요건을 충족했습니다.

### 왜 Vercel Client에서 MCP를 직접 호출하지 않았는가

MCP 서버 주소와 인증 토큰이 브라우저(Client Bundle)에 노출되면 누구나 그 값을 가지고 MCP 서버에 직접 요청을 보낼 수 있게 됩니다. 이를 막기 위해 LLM 호출, MCP 인증 토큰 사용, MCP 서버 호출을 모두 Next.js의 **서버 사이드(Route Handler, `app/api/chat/route.ts`)** 에서만 수행하고, 브라우저(Client Component)는 사용자 입력과 채팅 UI 표시만 담당하도록 구조를 분리했습니다.

### API Key와 Token은 어디에서 관리하는가

- `mcp_server/.env` (EC2 로컬에만 존재, Git에 커밋되지 않음): `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`, `MCP_AUTH_TOKEN`
- `.gitignore`, `.dockerignore` 양쪽 모두에 `.env`, `*.pem`을 등록하여 Git과 Docker 이미지 양쪽에서 credential이 노출되지 않도록 했습니다.
- Vercel 쪽 환경변수(`MCP_AUTH_TOKEN`, LLM API Key 등)는 `NEXT_PUBLIC_` 접두사를 사용하지 않고 서버 사이드 전용 환경변수로만 등록합니다. (담당: C)

캡처: `aws/mcp_tools.png` (Tool 목록 조회), `aws/mcp_call.png` (실제 Tool 호출 결과)

---

## Agent

Next.js(App Router) + Vercel로 구현했습니다. `/api/chat` Route Handler(서버 사이드)에서 Anthropic Claude(tool use)로 필요한 MCP Tool을 선택·호출하고, 그 결과를 다시 LLM에 전달해 최종 답변을 생성합니다. LLM이 직접 SQL을 만들거나 DB/MCP 서버에 접근하는 경로는 없으며, 항상 `lib/mcp`(MCP 클라이언트)를 거쳐서만 데이터에 접근합니다.

**단순 조회 예시**
```
사용자 질문: 현재 가장 최근 데이터는 뭐야?
→ 호출된 MCP Tool: get_latest_data(limit=10)
→ 조회된 DB 데이터: megabox 사이트 리뷰 최신 10건 (collected_at 2026-08-13 14:50:02 동일 수집 배치, review_date 2026-07-10~07-14, 평점 3.5~5.0)
→ Agent 답변: 최신 리뷰 10건을 표로 정리해 제시하고, 전부 megabox 데이터이며 평점이 대체로 4.0~5.0으로 높다는 특징을 함께 요약
```

**분석/집계 예시**
```
사용자 질문: 최근 일주일 평균 평점과 그 이전 일주일 평균을 비교해줘.
→ 호출된 MCP Tool: aggregate_data(site="megabox", start_date, end_date) — 오늘(2026-08-13) 기준 "최근 1주"에는 실제 리뷰 데이터가 0건임을 먼저 확인하고, 데이터가 존재하는 가장 최근 구간(2026-07-08~07-14 vs 07-01~07-07)으로 기간을 재조정하여 총 10회 호출
→ 조회된 DB 데이터: 최근 구간(07-08~07-14) megabox 83건 평균 4.60점 / 이전 구간(07-01~07-07) megabox 45건 평균 4.47점
→ Agent 답변: 데이터가 없는 기간을 임의로 답하지 않고 그 사실을 먼저 안내한 뒤, 실제 데이터가 있는 구간 기준으로 "평균 평점 0.14점 상승, 리뷰 건수 약 2배 증가"로 분석. naver/kinolights는 DB에 데이터가 없어 비교에서 제외한다고 명시
```

캡처: `aws/agent_query.png`, `aws/agent_analysis.png`

---

## 프로젝트 구조

```
YBIGTA_newbie_team_project/
├── collector/          # A 담당 — 데이터 수집
├── mcp_server/          # B 담당 — MCP 서버
│   ├── tools/
│   ├── services/
│   ├── repositories/
│   ├── server.py
│   ├── Dockerfile
│   └── requirements.txt
├── web/                 # C 담당 — Next.js Agent
│   ├── app/api/chat/route.ts
│   └── ...
├── aws/                  # 캡처 이미지 모음
├── .env.example
├── .gitignore
└── README.md
```

## 실행 방법

### MCP 서버 (Docker)

```bash
cd mcp_server
cp .env.example .env   # 실제 값 입력 후 사용
docker build -t mcp-server .
docker run -d --name mcp -p 127.0.0.1:8000:8000 --env-file .env mcp-server
```

Nginx가 80번 포트에서 리버스 프록시 + 인증을 처리하므로, 외부에서는 아래 형태로 접근합니다.

```bash
curl -H "Authorization: Bearer <MCP_AUTH_TOKEN>" http://<EC2 퍼블릭 IP>/sse
```

### MCP Tool 동작 확인 (MCP Inspector)

```bash
npx @modelcontextprotocol/inspector
```

- Transport: `sse`
- URL: `http://<EC2 퍼블릭 IP>/sse`
- Custom Header: `Authorization: Bearer <MCP_AUTH_TOKEN>`

### Data Analysis Agent (Next.js)

```bash
cd web
cp .env.example .env.local   # ANTHROPIC_API_KEY, MCP_SERVER_URL, MCP_AUTH_TOKEN 채우기
npm install
npm run dev
```

`http://localhost:3000` 접속 후 예시 질문을 입력하면 됩니다. `.env.local`의 `MCP_SERVER_URL`/`MCP_AUTH_TOKEN`이 비어있으면 자동으로 Mock 데이터(실제 MCP Tool 계약과 동일한 인터페이스)로 동작하므로, 서버가 아직 없을 때도 UI/Agent 로직 개발이 가능합니다.

---

## 주의사항 체크리스트

- [x] DB Port를 `0.0.0.0/0`으로 공개하지 않음
- [x] MCP에서 Raw SQL 실행 Tool을 제공하지 않음
- [x] MCP가 접근할 수 있는 데이터와 쿼리 범위를 제한함 (limit, 허용 파라미터)
- [x] DB는 Read-only Credential(`mcp_user`) 사용
- [x] MCP 내부 Port(8000)를 인터넷에 직접 노출하지 않음
- [x] API Key, MCP Token, DB Credential을 코드나 Client Bundle에 포함하지 않음
- [x] 새로운 데이터 소스나 Tool을 추가할 수 있도록 계층 구조로 확장 가능하게 설계
- [x] (C) Vercel Client에서 MCP를 직접 호출하지 않고 서버 사이드에서만 처리 — 구현 후 체크
