---
title: Marketplace API missing CORS middleware causes frontend Failed to fetch
date: 2026-05-28
category: docs/solutions/runtime-errors
module: marketplace-listing
problem_type: runtime_error
component: tooling
symptoms:
  - "Failed to fetch error in the marketplace review inbox (/marketplaces)"
  - "Browser blocks cross-origin requests to services/marketplace due to missing CORS headers"
root_cause: config_error
resolution_type: code_fix
severity: medium
tags: [cors, fastapi, nextjs, cross-origin, marketplace]
---

# Marketplace API missing CORS middleware causes frontend Failed to fetch

## Problem
When visiting the Marketplace Review Inbox (`/marketplaces`) or Accounts page (`/marketplaces/accounts`) in the frontend application running on `http://localhost:3000`, the page fails to load the drafts list or account settings and displays a generic `"Failed to fetch"` error.

## Symptoms
- In the browser developer console, network requests to `http://localhost/api/marketplace/drafts` or `http://localhost/api/marketplace/accounts` fail.
- Console error log shows: `Access to fetch at 'http://localhost/api/marketplace/drafts' from origin 'http://localhost:3000' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.`
- The frontend UI displays `Failed to fetch`.

## What Didn't Work
- Direct Nginx gateway configurations: While Nginx correctly proxies `/api/marketplace/` requests to the marketplace service container, it does not inject the required CORS headers for cross-origin local requests unless explicitly configured, which we avoid in favor of standard application-level CORS middleware.

## Solution
Configure `CORSMiddleware` in the marketplace service's FastAPI application `services/marketplace/main.py` to allow cross-origin requests from `http://localhost:3000` (frontend local port) and `http://localhost` (Nginx gateway).

```python
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Auto-Selp Marketplace Listing")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Why This Works
By default, the marketplace service is running as a separate service on port `8003` inside Docker, and standard requests from a local Next.js client running on `http://localhost:3000` are blocked by the browser's Same-Origin Policy. Adding Starlette's `CORSMiddleware` ensures that the server responds to cross-origin preflight and actual HTTP requests with correct `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, and other necessary headers.

## Prevention
- **CORS Consistency**: When spinning up new FastAPI microservices that will interact directly with the frontend client (even through Nginx proxying if the browser sees it as cross-origin or if it's on a different port), always configure `CORSMiddleware` at the application startup phase.
- **Reference existing services**: Refer to `services/auth/main.py` and `services/processor/main.py` which already implemented this pattern.

## Related Issues
- GitHub #52: Marketplace Submission & retry boundary.
