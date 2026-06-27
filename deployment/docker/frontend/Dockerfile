# ─────────────────────────────────────────────────────────────────────────────
# AI FinOps — Frontend Dockerfile
# Multi-stage: development → production
# ─────────────────────────────────────────────────────────────────────────────

# ─── Base ─────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS base

ENV PNPM_HOME="/pnpm" \
    PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /app

# ─── Development ──────────────────────────────────────────────────────────────
FROM base AS development

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install

COPY . .

EXPOSE 5173

CMD ["pnpm", "dev", "--host"]

# ─── Builder ──────────────────────────────────────────────────────────────────
FROM base AS builder

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# ─── Production ───────────────────────────────────────────────────────────────
FROM nginx:alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html
COPY ../nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
