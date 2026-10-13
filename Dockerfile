FROM node:22-slim AS dashboard
WORKDIR /build
RUN npm install -g bun@1
COPY dashboard/package.json dashboard/bun.lock* ./
RUN bun install --frozen-lockfile || bun install
COPY dashboard/ ./
RUN bun run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ROOT=/app PYTHONPATH=/app:/app/service
WORKDIR /app
COPY service/requirements.txt service/requirements.txt
RUN pip install --no-cache-dir -r service/requirements.txt
COPY jserisk jserisk
COPY service/app service/app
COPY data/research.json data/
COPY --from=dashboard /build/dist dashboard/dist
RUN useradd --uid 10001 app
USER app
WORKDIR /app/service
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
