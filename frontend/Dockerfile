# Next.js frontend for Cloud Run: install + build, then serve.
FROM node:22-slim AS build
WORKDIR /app

# Install dependencies against the lockfile for a reproducible build.
COPY package.json package-lock.json ./
RUN npm ci

# The backend Cloud Run URL is inlined into the client bundle at build time
# (NEXT_PUBLIC_* vars are baked by `next build`), so it must be set before build.
ARG NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

# Firebase web config — also baked at build time so Google sign-in works in the
# hosted bundle. These are public client identifiers, not secrets.
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
ARG NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID
ENV NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY
ENV NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ENV NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID
ENV NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=$NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
ENV NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=$NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ENV NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID

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
