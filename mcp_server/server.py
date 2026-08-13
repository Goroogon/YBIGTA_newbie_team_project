from mcp.server.fastmcp import FastMCP
from tools import search, latest, aggregation

# host, port는 생성자의 **settings로 전달
mcp = FastMCP("review-analysis-mcp", host="0.0.0.0", port=8000)

# Tool 등록
search.register(mcp)
latest.register(mcp)
aggregation.register(mcp)

if __name__ == "__main__":
    # mcp==1.2.0은 ASGI 앱을 직접 노출하지 않아 미들웨어 인증이 불가능하므로
    # Bearer Token 인증은 Nginx 리버스 프록시(nginx.conf)에서 처리함
    mcp.run(transport="sse")