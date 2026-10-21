#!/usr/bin/env python3
"""Copy GitLab job lifecycle metadata through its HTTP APIs into ClickHouse."""
import argparse
import datetime as dt
import json
import logging
import os
from pathlib import Path
import re
import signal
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
STOP = threading.Event()
LOG = logging.getLogger('gitlab-ci-collector')


class CollectorError(RuntimeError):
    """A diagnostic without credentials or upstream response bodies."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CollectorError('HTTP redirects are not allowed')


def utc(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def stamp(value):
    return value.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S.%f')


def setting(name, default, maximum):
    value = int(os.environ.get(name, default))
    if not 1 <= value <= maximum:
        raise ValueError(f'{name} is outside its allowed range')
    return value


class Collector:
    def __init__(self):
        self.source = os.environ.get('GITLAB_SOURCE', 'gitlab')
        self.database = os.environ.get('CLICKHOUSE_DATABASE', 'GitLabMetrics')
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', x) for x in (self.source, self.database)):
            raise ValueError('Invalid source or database identifier')
        self.url = os.environ.get('CLICKHOUSE_URL', 'http://clickhouse:8123').rstrip('/')
        parts = urllib.parse.urlsplit(self.url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('CLICKHOUSE_URL must be HTTP(S) without credentials or query')
        self.headers = {'X-ClickHouse-User': os.environ.get('CLICKHOUSE_USER', 'default'),
                        'X-ClickHouse-Key': os.environ.get('CLICKHOUSE_PASSWORD', '')}
        self.interval = setting('SYNC_INTERVAL_SECONDS', '60', 3600)
        self.days = setting('BACKFILL_DAYS', '30', 90)
        self.overlap = setting('RECHECK_SECONDS', '300', 86400)
        self.gitlab = os.environ.get('GITLAB_URL', 'https://gitlab.aiursoft.com').rstrip('/')
        parsed = urllib.parse.urlsplit(self.gitlab)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Invalid GITLAB_URL')
        self.token = os.environ.get('GITLAB_ACCESS_TOKEN', '')
        self.groups = [x.strip() for x in os.environ.get('GITLAB_GROUPS', '').split(',') if x.strip()]
        if any(not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', x) for x in self.groups):
            raise ValueError('Invalid GITLAB_GROUPS')
        self.rps = setting('API_REQUESTS_PER_SECOND', '2', 10)
        self.next_request = 0
        self.retry_after = 0
        self.requests = 0
        self.projects = None
        self.projects_expire = 0
        self.opener = urllib.request.build_opener(NoRedirect())

    def sql(self, query, rows=None):
        options = {'wait_end_of_query': '1', 'max_execution_time': '30', 'max_threads': '2'}
        if rows is None:
            body = query.encode()
        else:
            options['query'] = query
            body = ''.join(json.dumps(x, allow_nan=False) + '\n' for x in rows).encode()
        request = urllib.request.Request(self.url + '/?' + urllib.parse.urlencode(options), data=body,
                                         headers=self.headers, method='POST')
        try:
            with self.opener.open(request, timeout=45) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise CollectorError(f'ClickHouse HTTP status {error.code}') from None
        except (urllib.error.URLError, OSError, TimeoutError):
            raise CollectorError('ClickHouse request failed or timed out') from None

    def initialize(self):
        for query in Path(__file__).with_name('schema.sql').read_text().format(database=self.database).split(';'):
            if query.strip():
                self.sql(query)

    def api(self, path, payload=None):
        if not self.token:
            raise CollectorError('GITLAB_ACCESS_TOKEN is required')
        delay = self.next_request - time.monotonic()
        if delay > 0 and STOP.wait(delay):
            raise CollectorError('Collection interrupted')
        self.next_request = time.monotonic() + 1 / self.rps
        self.requests += 1
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {'PRIVATE-TOKEN': self.token, 'Content-Type': 'application/json'}
        request = urllib.request.Request(self.gitlab + path, data=body, headers=headers,
                                         method='POST' if body is not None else 'GET')
        try:
            with self.opener.open(request, timeout=45) as response:
                return json.loads(response.read()), response.headers.get('X-Next-Page', '')
        except urllib.error.HTTPError as error:
            if error.code == 429:
                value = error.headers.get('Retry-After', '60')
                self.retry_after = min(3600, max(60, int(value) if value.isdecimal() else 60))
            raise CollectorError(f'GitLab HTTP status {error.code}') from None
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            raise CollectorError('GitLab request failed or returned invalid JSON') from None

    def graphql(self, query):
        result, _ = self.api('/api/graphql', {'query': query})
        if not isinstance(result, dict) or result.get('errors') or not isinstance(result.get('data'), dict):
            raise CollectorError('GitLab GraphQL query failed')
        return result['data']

    def discover(self):
        if self.projects is not None and time.monotonic() < self.projects_expire:
            return self.projects
        if not self.groups:
            raise CollectorError('GITLAB_GROUPS is required')
        projects = {}
        for group in self.groups:
            page = '1'
            while page:
                query = urllib.parse.urlencode({'include_subgroups': 'true', 'with_shared': 'false',
                                                'simple': 'true', 'per_page': 100, 'page': page})
                rows, following = self.api('/api/v4/groups/' + urllib.parse.quote(group, safe='') + '/projects?' + query)
                if not isinstance(rows, list):
                    raise CollectorError('Invalid GitLab project list')
                for row in rows:
                    projects[int(row['id'])] = row['path_with_namespace']
                if following and (not following.isdecimal() or int(following) <= int(page)):
                    raise CollectorError('Invalid GitLab project pagination')
                page = following
        if not projects:
            raise CollectorError('No visible projects in the configured groups')
        self.projects, self.projects_expire = projects, time.monotonic() + 3600
        return projects

    @staticmethod
    def identifier(value, kind):
        match = re.fullmatch(r'gid://gitlab/' + re.escape(kind) + r'/(\d+)', value)
        if not match:
            raise CollectorError('Invalid GitLab object identifier')
        return int(match[1])

    def sync_pipeline(self, project_id, path, pipeline_id):
        count = 0
        # Query both retry states: prior attempts have their own IDs and must be retained.
        for retried in ('false', 'true'):
            after = None
            seen = set()
            while not STOP.is_set():
                query = ('{project(fullPath:' + json.dumps(path) + '){pipeline(id:' +
                         json.dumps('gid://gitlab/Ci::Pipeline/' + str(pipeline_id)) + '){id status '
                         'jobs(jobKind:BUILD,retried:' + retried + ',first:100,after:' + json.dumps(after) + '){'
                         'nodes{id name status queuedAt startedAt finishedAt webPath runner{id}} '
                         'pageInfo{endCursor hasNextPage}}}}}')
                project = self.graphql(query)['project']
                pipeline = project['pipeline'] if project else None
                if pipeline is None:
                    raise CollectorError('Pipeline is no longer visible')
                rows = []
                observed = stamp(dt.datetime.now(UTC))
                for job in pipeline['jobs']['nodes']:
                    q, s, f = [utc(job[key]) if job[key] else None
                               for key in ('queuedAt', 'startedAt', 'finishedAt')]
                    if (s and (q is None or s < q)) or (f and (s or q) and f < (s or q)):
                        raise CollectorError('Invalid API lifecycle timestamps')
                    if q and not f and job['status'] in ('SUCCESS', 'FAILED', 'CANCELED', 'SKIPPED'):
                        raise CollectorError('Queued terminal job has no finish time')
                    rows.append({'source': self.source, 'project_id': project_id, 'project_path': path,
                                 'pipeline_id': pipeline_id, 'pipeline_status': pipeline['status'].lower(),
                                 'job_id': self.identifier(job['id'], 'Ci::Build'), 'name': job['name'],
                                 'status': job['status'].lower(), 'web_path': job['webPath'],
                                 'runner_id': self.identifier(job['runner']['id'], 'Ci::Runner') if job['runner'] else None,
                                 'queued_at': stamp(q) if q else None, 'started_at': stamp(s) if s else None,
                                 'finished_at': stamp(f) if f else None, 'observed_at': observed})
                if rows:
                    self.sql(f'INSERT INTO {self.database}.api_jobs FORMAT JSONEachRow', rows)
                    count += len(rows)
                info = pipeline['jobs']['pageInfo']
                if not info['hasNextPage']:
                    break
                after = info['endCursor']
                if not after or after in seen:
                    raise CollectorError('Invalid GitLab job pagination')
                seen.add(after)
            if STOP.is_set():
                raise CollectorError('Collection interrupted')
        return count

    def sync(self, now=None):
        end = (now or dt.datetime.now(UTC)) - dt.timedelta(seconds=10)
        earliest = end - dt.timedelta(days=self.days)
        requests_before = self.requests
        projects = self.discover()
        progress = {int(row['project_id']): utc(row['through']) for row in self.records(
            f"SELECT project_id,max(through) AS through FROM {self.database}.api_project_sync "
            f"WHERE source='{self.source}' GROUP BY project_id FORMAT JSONEachRow")}
        active = {}
        for row in self.records(f"SELECT DISTINCT project_id,pipeline_id FROM {self.database}.api_jobs_latest "
                                f"WHERE source='{self.source}' AND pipeline_status IN "
                                "('created','pending','running','preparing','waiting_for_resource','waiting_for_callback','canceling') "
                                'FORMAT JSONEachRow'):
            active.setdefault(int(row['project_id']), set()).add(int(row['pipeline_id']))
        count = 0
        # Batch lightweight change discovery, never nested jobs for every project.
        items = list(projects.items())
        for offset in range(0, len(items), 10):
            pending = {}
            checkpoints = []
            for project_id, path in items[offset:offset + 10]:
                cursor = progress.get(project_id)
                if cursor and cursor > end:
                    raise CollectorError('Stored progress is ahead of collection')
                start = max(earliest, cursor - dt.timedelta(seconds=self.overlap)) if cursor else earliest
                pending[project_id] = {'path': path, 'start': start, 'after': {}, 'seen': set(), 'done': set(), 'pipelines': set()}
            while pending and not STOP.is_set():
                fields = []
                for project_id, entry in pending.items():
                    connections = []
                    for kind in ('regular', 'child'):
                        if kind in entry['done']:
                            continue
                        source = 'source:"parent_pipeline",' if kind == 'child' else ''
                        connections.append(kind + ':pipelines(' + source + 'updatedAfter:' +
                                           json.dumps(entry['start'].isoformat()) + ',updatedBefore:' +
                                           json.dumps(end.isoformat()) + ',first:20,after:' +
                                           json.dumps(entry['after'].get(kind)) + '){nodes{id} pageInfo{endCursor hasNextPage}}')
                    fields.append('p' + str(project_id) + ':project(fullPath:' +
                                  json.dumps(entry['path']) + '){' + ' '.join(connections) + '}')
                data = self.graphql('{' + ' '.join(fields) + '}')
                for project_id, entry in list(pending.items()):
                    project = data['p' + str(project_id)]
                    if project is None:
                        self.projects_expire = 0
                        raise CollectorError('Project is no longer visible')
                    for kind, page in project.items():
                        for pipeline in page['nodes']:
                            pipeline_id = self.identifier(pipeline['id'], 'Ci::Pipeline')
                            if pipeline_id not in entry['pipelines']:
                                count += self.sync_pipeline(project_id, entry['path'], pipeline_id)
                                entry['pipelines'].add(pipeline_id)
                        info = page['pageInfo']
                        if info['hasNextPage']:
                            after = info['endCursor']
                            if not after or (kind, after) in entry['seen']:
                                raise CollectorError('Invalid GitLab pipeline pagination')
                            entry['seen'].add((kind, after))
                            entry['after'][kind] = after
                        else:
                            entry['done'].add(kind)
                    if len(entry['done']) == 2:
                        for pipeline_id in active.get(project_id, set()) - entry['pipelines']:
                            count += self.sync_pipeline(project_id, entry['path'], pipeline_id)
                        if STOP.is_set():
                            raise CollectorError('Collection interrupted')
                        if project_id not in progress or entry['pipelines'] or active.get(project_id):
                            checkpoints.append({'source': self.source, 'project_id': project_id, 'through': stamp(end)})
                        del pending[project_id]
            if STOP.is_set():
                raise CollectorError('Collection interrupted')
            if checkpoints:
                self.sql(f'INSERT INTO {self.database}.api_project_sync FORMAT JSONEachRow', checkpoints)
        self.sql(f'INSERT INTO {self.database}.api_sync_runs FORMAT JSONEachRow',
                 [{'source': self.source, 'through': stamp(end), 'collected_at': stamp(dt.datetime.now(UTC)),
                   'project_ids': list(projects), 'groups': self.groups, 'requests': self.requests - requests_before}])
        LOG.info('API synchronization complete: %s projects, %s observations, %s requests',
                 len(projects), count, self.requests - requests_before)

    def records(self, query):
        return [json.loads(line) for line in self.sql(query).splitlines() if line.strip()]

    def health(self):
        rows = self.records(f"SELECT maxOrNull(collected_at) AS collected_at,maxOrNull(through) AS through "
                            f"FROM {self.database}.api_sync_runs WHERE source='{self.source}' FORMAT JSONEachRow")
        limit = self.interval * 3 + 300
        return all(rows[0][key] and 0 <= (dt.datetime.now(UTC) - utc(rows[0][key])).total_seconds() <= limit
                   for key in ('collected_at', 'through'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--init-schema', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--healthcheck', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    collector = Collector()
    if args.init_schema:
        collector.initialize()
        return 0
    if args.healthcheck:
        return 0 if collector.health() else 1
    while not STOP.is_set():
        try:
            collector.sync()
        except (CollectorError, ValueError, KeyError, TypeError):
            LOG.error('Collection failed; unconfirmed progress is retained')
            if args.once:
                return 1
        delay = max(collector.interval, collector.retry_after)
        collector.retry_after = 0
        if args.once or STOP.wait(delay):
            break
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (CollectorError, ValueError, KeyError, TypeError):
        LOG.error('Collector configuration or request failed')
        raise SystemExit(1)
