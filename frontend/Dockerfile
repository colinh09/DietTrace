# Next.js frontend for Cloud Run: install + build, then serve.
FROM node:22-slim AS build
WORKDIR /app

# Install dependencies against the lockfile for a reproducible build.
COPY package.json package-lock.json ./
RUN npm ci

# Build the Next app (next build).
COPY . .
RUN npm run build

# Runtime image: serve the built app.
FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app ./

# Cloud Run injects PORT (default 8080); next start binds to $PORT and 0.0.0.0.
ENV PORT=8080
EXPOSE 8080
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
