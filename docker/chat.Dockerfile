# Charie chat app image: built screens served by the FastAPI backend on one port.
# Build: docker build -f docker/chat.Dockerfile -t charie-chat .
# Run: docker compose --profile apps up --build chat (see docker-compose.yml).

FROM node:22-bookworm-slim AS screens
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY frontend/chat/package.json ./frontend/chat/
COPY frontend/learner/package.json ./frontend/learner/
COPY frontend/shared/package.json ./frontend/shared/
RUN npm ci --prefix frontend
COPY frontend/ ./frontend/
# Address of the other app for the cross-link on the login page.
ARG VITE_LEARNER_APP_URL=http://localhost:8081
ENV VITE_LEARNER_APP_URL=$VITE_LEARNER_APP_URL
RUN npm --prefix frontend run build --workspace @charie/chat

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
COPY --chown=charie:charie --from=screens /build/frontend/chat/dist /app/frontend/chat/dist
ENV PATH=/app/backend/.venv/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "charie.chat.app:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
