# ===========================================================================
# Stage 1: Build the React Application
# ===========================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for optimal Docker layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code and build production bundle
COPY . .
RUN npm run build

# ===========================================================================
# Stage 2: Serve with Nginx
# ===========================================================================
FROM nginx:alpine

# Copy built static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
