# CaseFlow Frontend

Next.js frontend for the CaseFlow workspace.

## What it includes

- sign-in and organization registration
- case list with search, status and priority counts, and a new-case form
- case detail page with documents, comments and activity log
- case assistant with thread history and cited sources

## Local development

1. Copy `.env.example` if you want a local reference.
2. Ensure the backend API is running on `http://127.0.0.1:8000`.
3. Run `npm install`.
4. Run `npm run dev`.
5. Open `http://127.0.0.1:3000`.

The frontend expects `NEXT_PUBLIC_API_BASE_URL` to point at the backend origin.

## Quality checks

- `npm run lint`
- `npm run build`
- `npm run e2e` (starts its own API on port 8001 and frontend on port 3001)

## Docker

The root `compose.yml` now includes the frontend service and exposes it on `http://127.0.0.1:3000`.
