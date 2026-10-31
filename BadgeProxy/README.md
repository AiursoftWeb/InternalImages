# GitLab Badge Proxy

Public pipeline and coverage SVGs for company projects, while GitLab stays internal.

Configure `GITLAB_URL` and `GITLAB_ACCESS_TOKEN` (read-only API access). Projects and default branches are discovered automatically under `aiursoft`; no project list is required. Use `/aiursoft/template/badges/master/pipeline.svg` or `coverage.svg`. Results share a one-minute bounded cache; unavailable data displays `unknown`. `/health` checks service availability.
