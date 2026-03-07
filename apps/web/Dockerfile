# LlamaTrade Web Frontend Dockerfile
# Build from repo root: docker build -f apps/web/Dockerfile -t web .

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files for workspace setup
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/

# Install all dependencies (workspaces)
RUN npm ci

# Copy web app source (includes pre-generated proto files)
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
