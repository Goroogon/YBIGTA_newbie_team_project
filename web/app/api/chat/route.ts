/**
 * Route Handler는 Vercel의 Server Side에서 실행됩니다.
 * ANTHROPIC_API_KEY, MCP_AUTH_TOKEN 등 민감한 값은 전부 여기(서버)에서만 사용되고,
 * 브라우저(Client Component)로는 절대 전달되지 않습니다. (과제 9번 요구사항)
 */
import { NextRequest, NextResponse } from "next/server";
import { runAgent } from "@/lib/llm";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청 형식입니다." }, { status: 400 });
  }

  const message = (body as { message?: unknown })?.message;
  if (typeof message !== "string" || message.trim().length === 0) {
    return NextResponse.json({ error: "message(string)가 필요합니다." }, { status: 400 });
  }
  if (message.length > 500) {
    return NextResponse.json({ error: "질문은 500자 이하로 입력해주세요." }, { status: 400 });
  }

  try {
    const result = await runAgent(message.trim());
    return NextResponse.json(result);
  } catch (err) {
    console.error("[api/chat] Agent 실행 중 오류:", err);
    return NextResponse.json({ error: "답변을 생성하는 중 오류가 발생했습니다." }, { status: 500 });
  }
}
