# LlamaTrade Web Frontend Dockerfile
# Build from repo root: docker build -f apps/web/Dockerfile -t web .

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Install buf CLI for proto generation
RUN apk add --no-cache curl \
    && curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.47.2/buf-Linux-x86_64" -o /usr/local/bin/buf \
    && chmod +x /usr/local/bin/buf

# Copy package files for workspace setup
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/

# Install all dependencies (workspaces)
RUN npm ci

# Copy proto files and generate TypeScript
COPY libs/proto ./libs/proto
RUN cd libs/proto && buf generate --template buf.gen.web.yaml

# Copy web app source
COPY apps/web ./apps/web

# Build the app
RUN npm run build --workspace=apps/web

# Production stage
FROM nginx:alpine

# Copy nginx config
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /app/apps/web/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
