CREATE DATABASE IF NOT EXISTS {database};
CREATE TABLE IF NOT EXISTS {database}.api_jobs
(
    source LowCardinality(String),
    project_id UInt64,
    project_path String,
    pipeline_id UInt64,
    pipeline_status LowCardinality(String),
    job_id UInt64,
    name String,
    status LowCardinality(String),
    web_path String,
    runner_id Nullable(UInt64),
    queued_at Nullable(DateTime64(3, 'UTC')),
    started_at Nullable(DateTime64(3, 'UTC')),
    finished_at Nullable(DateTime64(3, 'UTC')),
    observed_at DateTime64(6, 'UTC')
)
ENGINE = ReplacingMergeTree(observed_at)
ORDER BY (source, project_id, job_id);
CREATE VIEW IF NOT EXISTS {database}.api_jobs_latest AS
SELECT * FROM {database}.api_jobs FINAL;
CREATE TABLE IF NOT EXISTS {database}.api_project_sync
(
    source LowCardinality(String),
    project_id UInt64,
    through DateTime64(6, 'UTC')
)
ENGINE = MergeTree ORDER BY (source, project_id, through);
CREATE TABLE IF NOT EXISTS {database}.api_sync_runs
(
    source LowCardinality(String),
    through DateTime64(6, 'UTC'),
    collected_at DateTime64(6, 'UTC'),
    project_ids Array(UInt64),
    groups Array(String),
    requests UInt64
)
ENGINE = MergeTree ORDER BY (source, through);
