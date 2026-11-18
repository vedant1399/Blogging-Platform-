# Ink & Insight

A full-stack publishing platform for writing, discovering, and managing articles. The application is organized as a React/TypeScript client and a Flask REST API, with SQLite for local development and PostgreSQL for production.

> **Build status:** This repository is being assembled incrementally. The README describes the target application and the conventions the implementation follows; a capability is not available until its implementation is added.

## Contents

- [Architecture](#architecture)
- [Technology](#technology)
- [Requirements](#requirements)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Database and migrations](#database-and-migrations)
- [API conventions](#api-conventions)
- [Security](#security)
- [Testing and quality](#testing-and-quality)
- [Docker deployment](#docker-deployment)
- [Production checklist](#production-checklist)
- [Project layout](#project-layout)

## Architecture

The application separates presentation, HTTP transport, and domain behavior:

1. **Frontend (`frontend/`)** renders public publishing pages and authenticated author/admin experiences. Feature-specific UI and data access live together under `src/features/`; shared UI, routing, and infrastructure live in `src/components/`, `src/app/`, and `src/lib/`.
2. **API (`backend/app/api/v1/`)** validates requests, applies authentication and authorization, and serializes versioned JSON responses.
3. **Services (`backend/app/services/`)** implement business operations independently of Flask route handlers.
4. **Models (`backend/app/models/`)** define persistent entities and relationships through SQLAlchemy.
5. **Infrastructure (`deploy/`, root Docker files, and `.github/workflows/`)** configures the application for repeatable local development and production deployment.

The API is stateless for access-token authentication. Refresh credentials are handled separately from access tokens. Roles are `user`, `author`, and `admin`; unauthenticated visitors have the guest role. Permissions are enforced by the API, not merely hidden in the UI.

## Technology

| Area | Technologies |
| --- | --- |
| Client | React, TypeScript, Vite, Tailwind CSS, React Router |
| Client data/forms | TanStack Query, Axios, React Hook Form, Zod |
| Client experience | shadcn/ui, Framer Motion, React Hot Toast |
| API | Python, Flask, Flask-SQLAlchemy, Flask-Migrate |
| Authentication | Flask-JWT-Extended, Flask-Login integration where needed |
| Validation and abuse prevention | Flask-WTF, Flask-Limiter, explicit API validation |
| Database | SQLite (development), PostgreSQL (production) |
| Runtime | Gunicorn, Docker, Nginx |

Dependency versions are recorded in the project manifests and should be upgraded deliberately with the test suite passing.

## Requirements

For local development, install:

- Python 3.12 or later
- Node.js 20.19 or later (or 22.12 or later) and npm
- Git

Docker Desktop is required for the containerized PostgreSQL workflow. A local SQLite database does not require a separate database server.

## Local development

### 1. Configure environment variables

Copy `.env.example` to `.env` and set values appropriate for a local development environment. Never commit `.env` or production credentials.

### 2. Start the API

From the repository root, create and activate a virtual environment, install backend dependencies, initialize the database, and run Flask:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
flask --app backend.wsgi:app db upgrade
flask --app backend.wsgi:app run --debug
```

The development API listens on `http://127.0.0.1:5000` unless configured otherwise.

### 3. Start the client

In another terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Vite prints the client URL when it starts. By default, the Vite development server proxies `/api` requests to Flask at `http://127.0.0.1:5000`. To use another API origin, copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_BASE_URL`.

## Configuration

Configuration is supplied through environment variables. `.env.example` is the canonical list of names and safe local defaults. At minimum, production configuration must provide:

- A strong, unique Flask secret key
- A strong JWT signing key, separate from the Flask secret
- A PostgreSQL connection URL
- Explicit allowed frontend origins
- Secure cookie and HTTPS settings
- Mail transport credentials for registration verification and password recovery
- A persistent upload location and application-specific upload limits

Do not use development secrets, debug mode, or SQLite for a production deployment. Keep credentials in the deployment platform's secret manager rather than in source control.

## Database and migrations

SQLAlchemy models are defined under `backend/app/models/`. Schema changes are tracked using Flask-Migrate/Alembic; do not modify a deployed database schema manually.

Typical migration workflow:

```powershell
flask --app backend.wsgi:app db migrate -m "Describe schema change"
flask --app backend.wsgi:app db upgrade
```

Review generated migration scripts before applying them. Back up production data and test migrations against a staging database before deployment.

The model package includes UUID-keyed users, posts, categories, tags, comments, follows, likes, bookmarks, notifications, analytics events, and moderation reports. Posts have draft, scheduled, published, and archived states; comments support parent/reply relationships. Database constraints enforce unique post slugs, case-insensitive account/category/tag names, one like per user and target, and one bookmark per user/post pair. Analytics events record view, read, and share activity without storing raw IP addresses.

## API conventions

The REST API is versioned under `/api/v1`. JSON endpoints use the appropriate HTTP method and status code, validate input before performing writes, and return a consistent JSON error response. Collection endpoints are paginated; clients should not assume that a response contains every matching record.

The API surface is grouped by resource:

| Resource | Base path |
| --- | --- |
| Authentication | `/api/v1/auth` |
| Users and profiles | `/api/v1/users` |
| Posts | `/api/v1/posts` |
| Categories and tags | `/api/v1/categories`, `/api/v1/tags` |
| Comments | `/api/v1/posts/{post_id}/comments` |
| Likes and bookmarks | `/api/v1` |
| Notifications | `/api/v1/notifications` |
| Administration | `/api/v1/admin` |

The API's generated or maintained endpoint documentation will be added alongside the endpoint implementation. Clients must treat server-side authorization and validation as authoritative.

Account endpoints currently include `POST /api/v1/auth/register`, `/login`, `/refresh`, `/logout`, `/verify-email`, `/password-reset/request`, `/password-reset/confirm`, and `/password`; profile endpoints are `GET`, `PATCH`, and `DELETE /api/v1/users/me` plus `GET /api/v1/users/{username}`. The API returns short-lived access tokens for the `Authorization: Bearer` header and keeps rotating refresh tokens in an HttpOnly cookie. Unauthenticated or cookie-authenticated unsafe requests require the token returned by `GET /api/v1/csrf` in `X-CSRFToken`; the frontend API client obtains and attaches it automatically. Bearer-authenticated requests rely on the authorization header instead. Registration and password recovery require a configured mail transport.

## Security

The implementation follows these baseline requirements:

- Hash passwords with a modern adaptive password hash; never store plaintext passwords.
- Validate and normalize all user-controlled input at the API boundary.
- Use SQLAlchemy's parameterized query mechanisms rather than interpolating SQL.
- Apply authentication, role checks, ownership checks, and rate limits to protected operations.
- Protect cookie-authenticated state-changing requests against CSRF and configure cookies for `HttpOnly`, `Secure`, and an appropriate `SameSite` policy in production.
- Restrict CORS to explicitly configured trusted origins.
- Validate uploaded image MIME type, extension, and size; generate storage names and do not serve uploads as executable content.
- Return safe error messages to clients and keep sensitive diagnostic details in server-side logs.
- Use HTTPS, security response headers, secret rotation, and dependency updates in production.

Security controls must be verified in the route and deployment implementations; a checklist in documentation is not a substitute for enforcement.

## Testing and quality

Run backend tests from the repository root:

```powershell
python -m pytest backend\tests
```

Run frontend checks from `frontend/`:

```powershell
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

The backend and frontend test suites should cover domain behavior, API responses, validation, authorization, and the client flows that depend on them. CI runs the supported checks on changes. Coverage is measured by the configured test tooling; a coverage target is meaningful only when the suite exercises behavior rather than merely executing lines.

## Docker deployment

The production-oriented container setup is defined by `Dockerfile`, `docker-compose.yml`, and `deploy/`. Configure secrets and persistent storage before starting the stack. For local container development:

```powershell
docker compose up --build
```

Do not expose the database port publicly in production. Place the application behind HTTPS-terminating infrastructure, persist PostgreSQL data and user uploads, run database migrations as a controlled release step, and configure health checks, backups, logs, and monitoring.

## Production checklist

- [ ] Set unique production secrets using a secret manager.
- [ ] Configure PostgreSQL, backups, and tested restore procedures.
- [ ] Configure HTTPS, trusted origins, secure cookies, and security headers.
- [ ] Set upload limits and persistent, non-executable upload storage.
- [ ] Apply reviewed database migrations.
- [ ] Run backend and frontend tests and build the production client.
- [ ] Verify health checks, logging, monitoring, and alerting.
- [ ] Validate account recovery and email delivery configuration.
- [ ] Review rate limits, admin access, and authorization behavior.

## Project layout

```text
backend/
  app/
    api/v1/       Versioned HTTP endpoints
    core/         Application factory, configuration, extensions, errors
    models/       SQLAlchemy entities
    services/     Domain and application services
    storage/      Validated upload handling
    utils/        Shared backend utilities
  migrations/     Alembic migration history
  tests/          Backend tests
frontend/
  public/         Static public assets
  src/
    app/          Application setup, providers, and routing
    components/   Shared interface components
    features/     Feature-specific UI and data access
    hooks/        Reusable React hooks
    lib/          API client and shared utilities
    pages/        Route-level pages
    styles/       Global and theme styles
    test/         Frontend test setup and helpers
deploy/           Reverse proxy and application server configuration
.github/workflows/ CI workflows
```
