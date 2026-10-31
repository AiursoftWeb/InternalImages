# GitLab Badge Proxy

Public pipeline and coverage SVGs for explicitly allowed company projects, while GitLab stays internal.

Configure `GITLAB_URL`, `GITLAB_ACCESS_TOKEN` (read-only API access) and `ALLOWED_PROJECTS` (`template:master,kanban:master`). Requests use `/aiursoft/template/badges/master/pipeline.svg` or `coverage.svg`. Results share a one-minute cache; unavailable data displays `unknown`. `/health` checks service availability.
