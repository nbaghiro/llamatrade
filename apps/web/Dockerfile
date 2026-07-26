# LlamaTrade Web Frontend Dockerfile
# Build from repo root: docker build -f apps/web/Dockerfile -t web .

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files for a workspace-aware install. apps/web imports
# @llamatrade/core (apps/core), so its manifest must be present for npm ci to
# link the workspace.
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/
COPY apps/core/package.json ./apps/core/

# Install all dependencies (workspaces)
RUN npm ci

# Generate the TypeScript protos into @llamatrade/core. They are gitignored and
# dockerignored, so the image always builds them from the .proto sources rather
# than inheriting a host copy.
COPY libs/proto ./libs/proto
COPY apps/core ./apps/core
RUN npm run proto --workspace=apps/core

# Copy web app source (includes the Monolith design system under
# src/components + src/styles).
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
