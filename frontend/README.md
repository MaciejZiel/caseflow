# CaseFlow AI Frontend

Next.js frontend for the CaseFlow AI workspace.

## What it includes

- landing page with product positioning
- auth flows for register and login
- organization workspace dashboard
- case detail page with documents, comments and audit history
- grounded assistant UI with thread history and citations

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

## Docker

The root `compose.yml` now includes the frontend service and exposes it on `http://127.0.0.1:3000`.
