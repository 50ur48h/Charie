# Charie learner app image: built screens served by the FastAPI backend on one port.
# Runs forward migrations on start, then the API and the background learning job.
# Build: docker build -f docker/learner.Dockerfile -t charie-learner .
# Run: docker compose --profile apps up --build learner (see docker-compose.yml).
# One-off learning job: docker compose --profile apps run --rm learner-job

FROM node:22-bookworm-slim AS screens
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY frontend/chat/package.json ./frontend/chat/
COPY frontend/learner/package.json ./frontend/learner/
COPY frontend/shared/package.json ./frontend/shared/
RUN npm ci --prefix frontend
COPY frontend/ ./frontend/
# Address of the other app for the cross-link on the login page.
ARG VITE_CHAT_APP_URL=http://localhost:8080
ENV VITE_CHAT_APP_URL=$VITE_CHAT_APP_URL
RUN npm --prefix frontend run build --workspace @charie/learner

FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
RUN useradd -m -u 10001 charie
WORKDIR /app/backend
RUN chown charie:charie /app /app/backend
COPY --chown=charie:charie backend/pyproject.toml backend/uv.lock backend/.python-version ./
USER charie
RUN uv sync --frozen --no-dev --no-install-project && uv cache clean
COPY --chown=charie:charie backend/ ./
RUN uv sync --frozen --no-dev && uv cache clean
COPY --chown=charie:charie --from=screens /build/frontend/learner/dist /app/frontend/learner/dist
ENV PATH=/app/backend/.venv/bin:$PATH
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn charie.learner.app:app --host 0.0.0.0 --port 8000 --forwarded-allow-ips '*'"]
