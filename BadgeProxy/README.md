# GitLab Badge Proxy

Public pipeline and coverage SVGs for company projects, while GitLab stays internal.

Configure `GITLAB_URL` and `GITLAB_ACCESS_TOKEN` (read-only API access). Projects and default branches are discovered automatically under `aiursoft`; no project list is required. Use `/aiursoft/template/badges/master/pipeline.svg` or `coverage.svg`. Pipeline status comes from the latest pipeline on the default branch; coverage comes from the latest successful pipeline on that same branch. Coverage remains unknown if that successful pipeline has no coverage or no successful pipeline exists. A failed coverage lookup does not replace a known pipeline status. Responses use `no-store`; GitLab lookups share a bounded 30-minute server cache; unknown status or missing coverage shortens the shared cache to one minute. `/health` checks service availability.
