import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN")

if not MCP_AUTH_TOKEN:
    # 토큰이 아예 설정 안 된 채로 배포되는 사고를 막기 위한 안전장치
    raise RuntimeError("MCP_AUTH_TOKEN 환경변수가 설정되지 않았습니다. .env를 확인하세요.")


class AuthMiddleware(BaseHTTPMiddleware):
    """모든 요청에 대해 Authorization: Bearer <MCP_AUTH_TOKEN> 헤더를 검사한다.
    이 클래스가 server.py에서 add_middleware로 등록되어야 실제로 동작한다."""

    async def dispatch(self, request, call_next):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing or invalid Authorization header"},
                status_code=401,
            )

        token = auth_header.split(" ", 1)[1]
        if token != MCP_AUTH_TOKEN:
            return JSONResponse({"detail": "Invalid token"}, status_code=403)

        return await call_next(request)