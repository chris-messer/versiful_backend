# Versiful Backend – Context & Flows

This file is a quick primer for anyone jumping into a fresh LLM context. It summarizes what the app does, the user journey, and the key backend pieces you’ll need most often.

## What the product does
- Text-based biblical guidance for older / low-tech users.
- Users text a single number to receive scripture + gentle reflections.
- Accounts unlock unlimited guidance, saved history, preferences, and subscription management.

## High-level user journey (happy path)
1) Landing hero → “Get started” → `/signin` (web).
2) Signup or Sign in:
   - Email/password (`/auth/signup` then auto-login) or
   - Google (`identity_provider=Google` via Cognito hosted authorize URL).
3) `/callback` sets auth cookies via backend and checks `/users`:
   - If not registered: `/welcome` (collect phone + prefs) → PUT `/users`.
   - If registered but not subscribed: `/subscription` → PUT `/users` to set `isSubscribed/plan` (paid plans currently mocked client-side).
   - Else: `/settings`.
4) Settings shows subscription status, preferences (bible version, response style), and phone update (PUT `/users`).

## Backend pieces that matter
- API Gateway routes to Lambdas under `lambdas/`.
- Auth Lambda: `lambdas/auth/auth_handler.py`
  - `/auth/login` (POST): USER_PASSWORD_AUTH; sets `id_token`, `access_token`, `refresh_token` cookies (HttpOnly, Secure).
  - `/auth/signup` (POST): Cognito `sign_up`, attempts `admin_confirm_sign_up`, then USER_PASSWORD_AUTH and sets cookies.
  - `/auth/callback` (POST): OAuth code exchange (hosted UI / Google) → sets cookies.
  - `/auth/refresh` (POST): refresh via Cognito.
  - `/auth/logout` (POST): clears cookies.
  - CORS origin: `http://localhost:5173` in dev; `https://<domain>` otherwise.
- Users Lambda: `lambdas/users` (CRUD on user profile, phone, prefs, subscription flags). Frontend calls `POST /users` to ensure existence, `PUT /users` to update.
- JWT authorizer: `lambdas/authorizer/jwt_authorizer.py` for protected routes.

## Frontend expectations (so backend responses stay compatible)
- Auth cookies are expected after `/auth/login`, `/auth/signup`, `/auth/callback`, and `/auth/refresh`.
- `/users` JSON includes flags: `isRegistered`, `isSubscribed`, `plan`, `bibleVersion`, `phoneNumber`, `email`, `nextBillingDate` (optional).
- Free plan selection: PUT `/users` with `isSubscribed: true, plan: "free"`; paid plans currently mocked in UI (no checkout yet).
- Phone numbers: stored normalized as `+1##########`; UI formats for display.

## Environments and Terraform
- Terraform wrapper: `scripts/tf-env.sh <dev|staging|prod> <plan|apply ...>`.
- Cognito user pool client has no client secret; secret-hash not required.
- Callback URLs (dev): `http://localhost:5173/callback`; domains: `auth.dev.versiful.io`, `api.dev.versiful.io`.

## Quick testing notes
- Local frontend dev: Vite on 5173; backend expects cookies (`credentials: "include"`).
- Sign-in flows to test:
  - Email/password signup → `/users` POST/PUT → cookies present.
  - Email/password login with bad creds should return 401.
  - Google → `/callback` → cookies → `/welcome` or `/subscription` or `/settings`.
- Phone update: PUT `/users` with normalized `+1` number; ensure it round-trips.

## Open items / TODO
- Paid checkout still mocked on frontend; backend doesn’t handle payment webhooks yet.
- If international numbers are needed, extend phone normalization and formatting.

