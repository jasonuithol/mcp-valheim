FROM python:3.12-slim-bookworm

LABEL maintainer="claude-sandbox"
LABEL description="Valheim mod build tools MCP server"

# ── System dependencies ────────────────────────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    librsvg2-bin \
    && rm -rf /var/lib/apt/lists/*

# ── .NET SDK ───────────────────────────────────────────────────────────────────

RUN curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
       -o packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends dotnet-sdk-8.0 \
    && rm -rf /var/lib/apt/lists/*

# ── ilspycmd ───────────────────────────────────────────────────────────────────

ENV DOTNET_TOOLS="/root/.dotnet/tools"
ENV PATH="${DOTNET_TOOLS}:${PATH}"

RUN dotnet tool install -g ilspycmd --version 9.1.0.7988

# ── Python dependencies ────────────────────────────────────────────────────────

RUN pip install --no-cache-dir \
    fastmcp \
    httpx \
    "mcp-knowledge-base @ https://github.com/jasonuithol/mcp-knowledge-base/archive/refs/tags/v0.2.1.tar.gz"

# ── App ────────────────────────────────────────────────────────────────────────

WORKDIR /app
COPY mcp-service.py .

EXPOSE 5182

CMD ["python", "mcp-service.py"]
