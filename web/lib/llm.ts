/**
 * Agent 로직 (서버 사이드 전용).
 *
 * 과제 8번 요구사항: 사용자 질문 → Agent → MCP Tool 선택 → MCP Server → DB
 * → MCP Result → Agent → 최종 분석 결과 흐름을 반드시 거쳐야 하므로,
 * Anthropic의 tool use(=function calling)로 LLM이 MCP Tool 4개 중 필요한 것을
 * 스스로 선택/호출하게 하고, 그 결과를 다시 LLM에 넘겨 최종 답변을 생성합니다.
 *
 * LLM이 직접 SQL을 만들거나 DB에 접근하는 경로는 전혀 없고,
 * 오직 lib/mcp(getMcpClient)를 통해서만 데이터에 접근합니다.
 */
import "server-only";
import Anthropic from "@anthropic-ai/sdk";
import { getMcpClient } from "./mcp";
import {
  AggregateDataArgs,
  GetLatestDataArgs,
  SearchDataArgs,
} from "./mcp/types";

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
// claude-3-5-sonnet-20241022는 2026-08 기준 retire되어 404가 남 -> 현재 사용 가능한 별칭으로 교체.
// (claude-sonnet-5는 최신 dated 스냅샷으로 자동 resolve되는 alias)
const MODEL = process.env.ANTHROPIC_MODEL || "claude-sonnet-5";
const MAX_AGENT_TURNS = 6;

export interface ToolCallLog {
  tool: string;
  input: unknown;
  output: unknown;
  error?: string;
}

export interface AgentResult {
  answer: string;
  toolCalls: ToolCallLog[];
  mcpClientKind: "real" | "mock";
}

// MCP 서버(mcp_server/tools/*.py)의 Tool 정의와 이름·파라미터를 그대로 맞춘 Anthropic tool 스키마
const TOOLS: Anthropic.Tool[] = [
  {
    name: "search_data",
    description:
      "키워드와 기간으로 영화 리뷰를 검색합니다. 리뷰 본문에서 keyword가 부분 일치하는 데이터만 반환됩니다.",
    input_schema: {
      type: "object",
      properties: {
        keyword: { type: "string", description: "검색할 단어 (리뷰 본문 부분 일치)" },
        start_date: { type: "string", description: "YYYY-MM-DD" },
        end_date: { type: "string", description: "YYYY-MM-DD" },
        site: { type: "string", enum: ["megabox", "naver", "kinolights"], description: "생략 시 전체 사이트" },
        limit: { type: "integer", description: "최대 1~100건 (기본 20)" },
        offset: { type: "integer", description: "pagination용 시작 위치 (기본 0)" },
      },
      required: ["keyword", "start_date", "end_date"],
    },
  },
  {
    name: "get_latest_data",
    description: "가장 최근에 수집된 리뷰 데이터를 조회합니다. (실제로 데이터가 최신인지 확인할 때 사용)",
    input_schema: {
      type: "object",
      properties: {
        site: { type: "string", enum: ["megabox", "naver", "kinolights"], description: "생략 시 전체 사이트" },
        limit: { type: "integer", description: "최대 1~100건 (기본 10)" },
      },
    },
  },
  {
    name: "aggregate_data",
    description: "특정 사이트, 특정 기간의 리뷰 평균 평점과 리뷰 수를 집계합니다.",
    input_schema: {
      type: "object",
      properties: {
        site: { type: "string", enum: ["megabox", "naver", "kinolights"] },
        start_date: { type: "string", description: "YYYY-MM-DD" },
        end_date: { type: "string", description: "YYYY-MM-DD" },
      },
      required: ["site", "start_date", "end_date"],
    },
  },
  {
    name: "get_available_sites",
    description: "현재 DB에 수집되어 있는 사이트(megabox/naver/kinolights) 목록을 조회합니다.",
    input_schema: { type: "object", properties: {} },
  },
];

async function callMcpTool(name: string, input: unknown): Promise<unknown> {
  const mcp = getMcpClient();
  switch (name) {
    case "search_data":
      return mcp.searchData(input as SearchDataArgs);
    case "get_latest_data":
      return mcp.getLatestData((input ?? {}) as GetLatestDataArgs);
    case "aggregate_data":
      return mcp.aggregateData(input as AggregateDataArgs);
    case "get_available_sites":
      return mcp.getAvailableSites();
    default:
      throw new Error(`알 수 없는 MCP Tool: ${name}`);
  }
}

function systemPrompt(): string {
  const today = new Date().toISOString().slice(0, 10);
  return [
    "당신은 YBIGTA 신입기수 팀 프로젝트의 영화 리뷰 데이터 분석 Agent입니다.",
    "megabox, naver, kinolights 세 사이트에서 수집된 실제 리뷰 DB 데이터를 다룹니다.",
    "",
    "규칙:",
    "1. 데이터에 대한 질문에는 반드시 제공된 Tool(search_data, get_latest_data, aggregate_data, get_available_sites)을 호출해서 실제 DB 데이터를 조회한 뒤 답변하세요.",
    "2. 이미 알고 있는 일반 상식이나 추측만으로 데이터 관련 질문에 답하지 마세요.",
    "3. '최근 N일', '이번 주' 같은 상대적 기간 질문은 오늘 날짜(" + today + ") 기준으로 직접 start_date/end_date를 계산해서 Tool을 호출하세요.",
    "4. 기간 비교(예: 이번 주 vs 지난 주 평균 비교)가 필요하면 aggregate_data를 기간을 나눠 두 번 이상 호출한 뒤 결과를 비교해서 설명하세요.",
    "5. 답변은 한국어로, 근거가 된 수치(평균 평점, 건수 등)를 함께 제시하세요.",
  ].join("\n");
}

export async function runAgent(userMessage: string): Promise<AgentResult> {
  const mcp = getMcpClient();
  const toolCalls: ToolCallLog[] = [];
  const messages: Anthropic.MessageParam[] = [{ role: "user", content: userMessage }];

  for (let turn = 0; turn < MAX_AGENT_TURNS; turn++) {
    const response = await anthropic.messages.create({
      model: MODEL,
      max_tokens: 1024,
      system: systemPrompt(),
      tools: TOOLS,
      messages,
    });

    messages.push({ role: "assistant", content: response.content });

    const toolUseBlocks = response.content.filter(
      (block): block is Anthropic.ToolUseBlock => block.type === "tool_use"
    );

    if (toolUseBlocks.length === 0) {
      const answer = response.content
        .filter((block): block is Anthropic.TextBlock => block.type === "text")
        .map((block) => block.text)
        .join("\n")
        .trim();
      return { answer: answer || "답변을 생성하지 못했습니다.", toolCalls, mcpClientKind: mcp.kind };
    }

    const toolResultBlocks: Anthropic.ToolResultBlockParam[] = [];
    for (const block of toolUseBlocks) {
      try {
        const output = await callMcpTool(block.name, block.input);
        toolCalls.push({ tool: block.name, input: block.input, output });
        toolResultBlocks.push({
          type: "tool_result",
          tool_use_id: block.id,
          content: JSON.stringify(output),
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        toolCalls.push({ tool: block.name, input: block.input, output: null, error: message });
        toolResultBlocks.push({
          type: "tool_result",
          tool_use_id: block.id,
          content: JSON.stringify({ error: message }),
          is_error: true,
        });
      }
    }
    messages.push({ role: "user", content: toolResultBlocks });
  }

  return {
    answer: "여러 차례 시도했지만 답변을 완성하지 못했습니다. 질문을 조금 더 구체적으로 해주세요.",
    toolCalls,
    mcpClientKind: mcp.kind,
  };
}
