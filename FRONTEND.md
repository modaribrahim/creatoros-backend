# CreatorOS — Frontend Handoff (new backend URL)

Handoff for the frontend developer after migrating off Render to a self-hosted
VPS. Read this together with the full endpoint reference in **`API.md`**.

---

## 1. New backend base URL

```
https://creatoros-api.45.59.120.101.sslip.io
```

- **HTTPS only** (mandatory — the frontend is served from Vercel over HTTPS, and
  browsers block mixed content). Never call `http://45.59.120.101` directly.
- All API paths are prefixed with `/api/v1` just like before (routes unchanged).
- FastAPI interactive docs (OpenAPI/Swagger) live at:
  `https://creatoros-api.45.59.120.101.sslip.io/docs`
- Health check: `GET https://creatoros-api.45.59.120.101.sslip.io/health` → `200`

### Required change (one line)

Update your API base URL config from:

```
https://creatoros-api-y97d.onrender.com
```

to:

```
https://creatoros-api.45.59.120.101.sslip.io
```

The endpoint paths, request/response shapes, and auth flow are **unchanged**.
This is the only change required to switch environments.

---

## 2. CORS — what's allowed

The backend is locked down to a **single** allowed origin (CORS whitelist):

```
https://creator-pilot-virid.vercel.app
```

- The origin must match **exactly**, with **no trailing slash**.
- Requests from any other origin (a different Vercel app, local `localhost:5173`,
  or a custom domain) will be **blocked** by CORS with no `Access-Control-Allow-Origin`
  header.
- If the frontend's Vercel URL changes (new project name / custom domain), the
  backend env var `FRONTEND_URL` must be updated and the containers restarted.
  Get in touch so that's done together.

How to check CORS is the problem: open DevTools → Console/Network. A blocked
request shows `CORS policy: No 'Access-Control-Allow-Origin' header is present`.

---

## 3. Auth flow (unchanged, for reference)

1. `POST /api/v1/auth/signup` or `/auth/login` → returns `tokens`
   (`access_token`, `refresh_token`) + `user`.
2. Send `Authorization: Bearer <access_token>` on every other request.
3. When the access token expires (HTTP `401`), call
   `POST /api/v1/auth/refresh` with `{ "refresh_token": ... }` to get a new pair.
4. `POST /api/v1/auth/logout` with `{ "refresh_token": ... }` on sign-out.

Full payloads/logic are in `API.md`.

---

## 4. Environment summary

| Setting | Value |
|---|---|
| Backend base URL | `https://creatoros-api.45.59.120.101.sslip.io` |
| Allowed frontend origin | `https://creator-pilot-virid.vercel.app` (no trailing slash) |
| Docs | `https://creatoros-api.45.59.120.101.sslip.io/docs` |
| Path prefix | `/api/v1` |
| Scheme | HTTPS only |
| Managed services (no frontend impact) | Neon Postgres, Upstash Redis |

---

## 5. Notes / gotchas

- **Cert is auto-managed** (Let's Encrypt via Caddy, auto-renews). No action needed.
- **Trailing slash on URLs**: keep paths exact; a trailing slash on the origin
  (`...vercel.app/`) is what breaks CORS — make sure the configured origin has none.
- **Rate/size limits**: backend caps analysis at `MAX_COMMENTS` (default 300) per
  job; the chat tool has a similar cap. Large comment dumps are chunked server-side.
- The API, worker (background jobs), and TLS are three containers on the same VPS.
  A job is submitted, tracked by `job_id`, and polled via
  `GET /api/v1/jobs/{job_id}` — same polling flow as before.
