FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY main.py ./
COPY app/ ./app/
COPY lib/ ./lib/
COPY jobs/ ./jobs/

EXPOSE 9000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
