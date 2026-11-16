"""Durable, bounded synthesis queue. Only the elected child process imports IndexTTS."""
import asyncio
import contextlib
import ctypes
import fcntl
import json
import logging
import multiprocessing
import os
from pathlib import Path
import sqlite3
import signal
import time
import uuid

logger = logging.getLogger(__name__)


class QueueFull(Exception):
    pass


class JobQueue:
    def __init__(self, data_dir, capacity=100, attempts=3, retention=604800, results_limit=2000):
        self.root = Path(data_dir) / 'tts_jobs'
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.results = self.root / 'results'
        self.results.mkdir(exist_ok=True, mode=0o700)
        self.database = self.root / 'queue.sqlite3'
        self.capacity, self.max_attempts = capacity, attempts
        self.retention, self.results_limit = retention, results_limit
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL, status TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL DEFAULT 0,
                    started REAL, progress INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0, output TEXT, error TEXT,
                    cache_hit INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS pending ON jobs(status, available, created);
                CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY CHECK(id=1), info TEXT NOT NULL);
            ''')
        os.chmod(self.database, 0o600)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=2)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _prune(self, db):
        rows = db.execute('''SELECT id, output, updated FROM jobs WHERE status IN ('completed','failed')
            ORDER BY updated DESC, id''').fetchall()
        cutoff = time.time() - self.retention
        for i, row in enumerate(rows):
            updated = row['updated']
            if i < self.results_limit and updated >= cutoff:
                continue
            db.execute('DELETE FROM jobs WHERE id=?', (row['id'],))
            for artifact in self.results.glob(row['id'] + '.*'):
                artifact.unlink(missing_ok=True)

    def submit(self, fingerprint, payload, cached_source=None):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._prune(db)
            old = db.execute('SELECT * FROM jobs WHERE fingerprint=?', (fingerprint,)).fetchone()
            if old and (old['status'] in ('queued', 'running') or
                        (old['status'] == 'completed' and self.output_exists(old))):
                if old['status'] == 'completed':
                    db.execute('UPDATE jobs SET cache_hit=1,updated=? WHERE id=?', (now, old['id']))
                    old = db.execute('SELECT * FROM jobs WHERE id=?', (old['id'],)).fetchone()
                return self.public(db, old)
            # A terminal failure is stable until the caller explicitly submits again.
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            cached_source = Path(cached_source) if cached_source else None
            if count >= self.capacity and not (cached_source and cached_source.is_file()):
                raise QueueFull()
            if old:
                db.execute('''UPDATE jobs SET status='queued', updated=?, attempts=0, available=0,
                    started=NULL, progress=0, total=0, output=NULL, error=NULL, cache_hit=0 WHERE id=?''',
                           (now, old['id']))
                ident = old['id']
            else:
                ident = uuid.uuid4().hex
                db.execute('''INSERT INTO jobs(id,fingerprint,payload,status,created,updated)
                    VALUES(?,?,?,'queued',?,?)''', (ident, fingerprint, json.dumps(payload), now, now))
            if cached_source and cached_source.is_file():
                try:
                    filename = self.retain(ident, payload['response_format'], cached_source)
                    db.execute("UPDATE jobs SET status='completed',output=?,cache_hit=1 WHERE id=?",
                               (filename, ident))
                except FileNotFoundError:
                    # A concurrent explicit cache clear is allowed to turn a hit into a miss.
                    if count >= self.capacity:
                        raise QueueFull()
            return self.public(db, db.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone())

    def output_exists(self, row):
        return bool(row['output'] and (self.results / Path(row['output']).name).is_file())

    def public(self, db, row):
        position = None
        status = row['status']
        if status == 'queued':
            position = 1 + db.execute("""SELECT COUNT(*) FROM jobs WHERE status='queued'
                AND (created < ? OR (created=? AND id < ?))""",
                                     (row['created'], row['created'], row['id'])).fetchone()[0]
        if status == 'completed' and not self.output_exists(row):
            status = 'expired'
        return {'id': row['id'], 'status': status, 'queue_position': position,
                'completed_segments': row['progress'], 'total_segments': row['total'],
                'attempts': row['attempts'], 'error': row['error'],
                'cache_hit': bool(row['cache_hit'])}

    def get(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
            return self.public(db, row) if row else None

    def audio(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND status='completed'", (ident,)).fetchone()
            if row and self.output_exists(row):
                return self.results / row['output'], json.loads(row['payload'])['response_format']
        return None

    def recover(self):
        with self.connect() as db:
            for row in db.execute("SELECT * FROM jobs WHERE status='running'").fetchall():
                payload = json.loads(row['payload'])
                extension = 'raw' if payload['response_format'] == 'pcm' else payload['response_format']
                filename = row['id'] + '.' + extension
                if (self.results / filename).is_file():
                    db.execute("UPDATE jobs SET status='completed',output=?,error=NULL,updated=? WHERE id=?",
                               (filename, time.time(), row['id']))
                else:
                    failed = row['attempts'] >= self.max_attempts
                    db.execute("UPDATE jobs SET status=?,error=?,updated=?,started=NULL,available=0 WHERE id=?",
                               ('failed' if failed else 'queued',
                                'Worker stopped repeatedly; please retry.' if failed else None,
                                time.time(), row['id']))
            self._prune(db)

    def retain(self, ident, fmt, source):
        extension = 'raw' if fmt == 'pcm' else fmt
        destination = self.results / (ident + '.' + extension)
        temporary = destination.with_suffix(destination.suffix + '.' + uuid.uuid4().hex + '.partial')
        try:
            os.link(source, temporary)
            with temporary.open('rb') as f:
                os.fsync(f.fileno())
            os.replace(temporary, destination)
            directory = os.open(self.results, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return destination.name

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("""SELECT * FROM jobs WHERE status='queued' AND available<=?
                ORDER BY created,id LIMIT 1""", (time.time(),)).fetchone()
            if row:
                db.execute("""UPDATE jobs SET status='running', attempts=attempts+1,
                    started=?,updated=?,progress=0,total=0 WHERE id=?""", (time.time(), time.time(), row['id']))
                return dict(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())
        return None

    def progress(self, ident, done, total):
        with self.connect() as db:
            db.execute('UPDATE jobs SET progress=?,total=?,updated=? WHERE id=?',
                       (done, total, time.time(), ident))

    def finish(self, ident, output, cache_hit):
        with self.connect() as db:
            db.execute("""UPDATE jobs SET status='completed',output=?,cache_hit=?,updated=?,
                progress=total,error=NULL WHERE id=?""", (output, int(cache_hit), time.time(), ident))

    def fail(self, job, retry=True):
        retry = retry and job['attempts'] < self.max_attempts
        with self.connect() as db:
            db.execute('''UPDATE jobs SET status=?,error=?,available=?,updated=? WHERE id=?''',
                       ('queued' if retry else 'failed',
                        'Synthesis failed; retrying.' if retry else 'Synthesis failed; please retry.',
                        time.time() + min(60, 2 ** job['attempts']), time.time(), job['id']))

    def info(self, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO worker(id,info) VALUES(1,?)', (json.dumps(value),))
                return value
            row = db.execute('SELECT info FROM worker WHERE id=1').fetchone()
            return json.loads(row[0]) if row else {'state': 'starting'}

    def active_started(self):
        with self.connect() as db:
            row = db.execute("SELECT MIN(started) FROM jobs WHERE status='running'").fetchone()
            return row[0]


def run_worker(data_dir, settings, stop):
    """A file lock elects exactly one GPU worker for this local persistent volume."""
    # Linux containers must not retain a GPU-owning orphan after the HTTP process is killed.
    parent = os.getppid()
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM) != 0:
        raise OSError(ctypes.get_errno(), 'Cannot set worker parent-death signal.')
    if os.getppid() != parent:
        return
    queue = JobQueue(data_dir, **settings)
    with (queue.root / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        queue.recover()
        queue.info({'state': 'starting'})
        import main as engine
        engine.initialize_model()
        info = {**engine.system_info, 'state': 'ready' if engine.tts_model is not None else 'failed',
                'model_loaded': engine.tts_model is not None,
                'model_runtime_device': engine.model_runtime_device,
                'cuda_fallback_to_cpu': engine.cuda_fallback_to_cpu,
                'model_init_error': engine.model_init_error}
        queue.info(info)
        if engine.tts_model is None:
            return
        while not stop.is_set():
            job = queue.claim()
            if job is None:
                stop.wait(.25)
                continue
            payload = json.loads(job['payload'])
            fmt = payload.pop('response_format')
            extension = 'raw' if fmt == 'pcm' else fmt
            destination = queue.results / (job['id'] + '.' + extension)
            try:
                # A process can stop after publishing audio but before committing completion.
                if destination.is_file():
                    queue.finish(job['id'], destination.name, True)
                    continue
                def progress(done, total):
                    queue.progress(job['id'], done, total)
                    if stop.is_set():
                        raise InterruptedError('Worker is stopping.')
                source, hit = engine._perform_tts(**payload, progress=progress)
                if fmt != 'wav':
                    converted = source + '.' + extension
                    if not Path(converted).is_file():
                        engine.convert_audio(source, converted, fmt)
                    source = converted
                filename = queue.retain(job['id'], fmt, source)
                queue.finish(job['id'], filename, hit)
                engine.cleanup_output_audios()
            except InterruptedError:
                # Recovery on the next elected worker releases the running claim.
                return
            except Exception as error:
                logger.exception('TTS job %s failed.', job['id'])
                status = getattr(error, 'status_code', None)
                queue.fail(job, retry=status is None or status >= 500)
                # Recreate a CUDA context after a fatal inference error.
                if 'cuda' in str(error).lower():
                    return


class WorkerSupervisor:
    def __init__(self, data_dir, queue, settings, job_timeout=900, load_timeout=300):
        self.data_dir, self.queue, self.settings = data_dir, queue, settings
        self.job_timeout, self.load_timeout = job_timeout, load_timeout
        self.process = None
        self.stop_event = None
        self.task = None
        self.started = 0
        self.context = multiprocessing.get_context('spawn')

    def start(self):
        self.task = asyncio.create_task(self.monitor())

    async def monitor(self):
        while True:
            if self.process is None or not self.process.is_alive():
                if self.process is not None:
                    self.process.join()
                    self.process.close()
                    self.stop_event = None
                    await asyncio.sleep(5)
                self.stop_event = self.context.Event()
                self.process = self.context.Process(target=run_worker,
                    args=(self.data_dir, self.settings, self.stop_event), daemon=True)
                self.process.start()
                self.started = time.time()
            info = await asyncio.to_thread(self.queue.info)
            active = await asyncio.to_thread(self.queue.active_started)
            timed_out = (active is not None and time.time() - active > self.job_timeout) or (
                info.get('state') != 'ready' and time.time() - self.started > self.load_timeout)
            if timed_out:
                logger.error('TTS worker exceeded its execution deadline; recovering queued work.')
                self.process.terminate()
                await asyncio.to_thread(self.process.join, 5)
                if self.process.is_alive():
                    self.process.kill()
                    await asyncio.to_thread(self.process.join)
            await asyncio.sleep(1)

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        if self.process:
            self.stop_event.set()
            await asyncio.to_thread(self.process.join, 15)
            if self.process.is_alive():
                self.process.terminate()
                await asyncio.to_thread(self.process.join, 5)
            if self.process.is_alive():
                self.process.kill()
                await asyncio.to_thread(self.process.join)
            self.process.close()
            self.process = None
            self.stop_event = None
        self.task = None
