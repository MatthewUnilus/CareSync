# Build stage
FROM node:22-slim AS build

WORKDIR /app

# Copy root package files (workspace setup)
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/

# Install dependencies
RUN npm ci

# Copy frontend source
COPY frontend/ frontend/

# Build with the API URL injected at build time
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build:web

# Serve stage — lightweight static server
FROM node:22-slim

RUN npm install -g serve@14

COPY --from=build /app/frontend/dist /app/dist

EXPOSE 3000

CMD ["serve", "-s", "/app/dist", "-l", "3000"]
