from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PATCH_PATH = Path(__file__).with_name("sitecustomize.py")


class SiteCustomizeRefreshTests(unittest.IsolatedAsyncioTestCase):
    def _load_patch(
        self,
        *,
        load_credentials,
        is_expired,
        upstream_ensure,
        credentials_file: Path,
        preloaded_server: bool = False,
    ):
        package = types.ModuleType("codex_proxy")
        package.__path__ = []

        config = types.ModuleType("codex_proxy.config")
        config.CODEX_MODELS = []

        auth = types.ModuleType("codex_proxy.auth")
        auth.CREDENTIALS_FILE = credentials_file
        auth.load_credentials = load_credentials
        auth.is_expired = is_expired
        auth.ensure_credentials = upstream_ensure

        modules = {
            "codex_proxy": package,
            "codex_proxy.config": config,
            "codex_proxy.auth": auth,
        }
        server = None
        if preloaded_server:
            server = types.ModuleType("codex_proxy.server")
            server.ensure_credentials = upstream_ensure
            modules["codex_proxy.server"] = server

        module_name = f"_sitecustomize_test_{id(auth)}"
        spec = importlib.util.spec_from_file_location(module_name, PATCH_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)

        return module, auth, server

    async def test_unexpired_credentials_use_fast_path(self):
        credentials = {"access_token": "fresh"}
        upstream_calls = 0

        async def upstream(path):
            nonlocal upstream_calls
            upstream_calls += 1
            return credentials

        _, auth, _ = self._load_patch(
            load_credentials=lambda path: credentials,
            is_expired=lambda value: False,
            upstream_ensure=upstream,
            credentials_file=Path("credentials.json"),
        )

        self.assertIs(await auth.ensure_credentials(), credentials)
        self.assertEqual(upstream_calls, 0)

    async def test_same_canonical_path_refreshes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "credentials.json"
            state = {"credentials": {"access_token": "expired"}}
            upstream_calls = 0

            def load_credentials(path):
                return state["credentials"]

            def is_expired(credentials):
                return credentials["access_token"] == "expired"

            async def upstream(path):
                nonlocal upstream_calls
                credentials = load_credentials(path)
                if not is_expired(credentials):
                    return credentials
                upstream_calls += 1
                await asyncio.sleep(0.01)
                state["credentials"] = {"access_token": "fresh"}
                return state["credentials"]

            _, auth, _ = self._load_patch(
                load_credentials=load_credentials,
                is_expired=is_expired,
                upstream_ensure=upstream,
                credentials_file=canonical,
            )

            aliases = [canonical, root / "." / "credentials.json"] * 4
            results = await asyncio.gather(*(auth.ensure_credentials(path) for path in aliases))

            self.assertEqual(upstream_calls, 1)
            self.assertTrue(all(result["access_token"] == "fresh" for result in results))

    async def test_different_paths_refresh_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / "a.json", Path(directory) / "b.json"]
            entered: set[Path] = set()
            both_entered = asyncio.Event()

            async def upstream(path):
                entered.add(path)
                if len(entered) == 2:
                    both_entered.set()
                await asyncio.wait_for(both_entered.wait(), timeout=1)
                return {"access_token": "fresh"}

            _, auth, _ = self._load_patch(
                load_credentials=lambda path: {"access_token": "expired"},
                is_expired=lambda credentials: True,
                upstream_ensure=upstream,
                credentials_file=paths[0],
            )

            await asyncio.gather(*(auth.ensure_credentials(path) for path in paths))
            self.assertEqual(entered, set(paths))

    async def test_exception_releases_lock_for_next_call(self):
        calls = 0

        async def upstream(path):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("refresh failed")
            return {"access_token": "fresh"}

        _, auth, _ = self._load_patch(
            load_credentials=lambda path: {"access_token": "expired"},
            is_expired=lambda credentials: True,
            upstream_ensure=upstream,
            credentials_file=Path("credentials.json"),
        )

        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            await auth.ensure_credentials()
        self.assertEqual((await auth.ensure_credentials())["access_token"], "fresh")
        self.assertEqual(calls, 2)

    async def test_preloaded_server_binding_and_reload_are_idempotent(self):
        async def upstream(path):
            return {"access_token": "fresh"}

        module, auth, server = self._load_patch(
            load_credentials=lambda path: {"access_token": "fresh"},
            is_expired=lambda credentials: False,
            upstream_ensure=upstream,
            credentials_file=Path("credentials.json"),
            preloaded_server=True,
        )
        wrapper = auth.ensure_credentials
        self.assertIs(server.ensure_credentials, wrapper)

        modules = {
            "codex_proxy": sys.modules.get("codex_proxy", types.ModuleType("codex_proxy")),
            "codex_proxy.config": module._config,
            "codex_proxy.auth": auth,
            "codex_proxy.server": server,
        }
        modules["codex_proxy"].__path__ = []
        spec = importlib.util.spec_from_file_location("_sitecustomize_test_reload", PATCH_PATH)
        reloaded = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(reloaded)

        self.assertIs(auth.ensure_credentials, wrapper)
        self.assertIs(server.ensure_credentials, wrapper)
        self.assertIs(
            getattr(wrapper, "_codex_proxy_upstream_ensure_credentials"),
            upstream,
        )


class SiteCustomizeLoopIsolationTests(unittest.TestCase):
    def test_separate_event_loops_do_not_share_asyncio_lock(self):
        state = {"credentials": {"access_token": "expired"}}
        calls = 0

        def load_credentials(path):
            return state["credentials"]

        def is_expired(credentials):
            return credentials["access_token"] == "expired"

        async def upstream(path):
            nonlocal calls
            credentials = load_credentials(path)
            if not is_expired(credentials):
                return credentials
            calls += 1
            await asyncio.sleep(0)
            state["credentials"] = {"access_token": "fresh"}
            return state["credentials"]

        helper = SiteCustomizeRefreshTests()
        _, auth, _ = helper._load_patch(
            load_credentials=load_credentials,
            is_expired=is_expired,
            upstream_ensure=upstream,
            credentials_file=Path("credentials.json"),
        )

        async def contend():
            state["credentials"] = {"access_token": "expired"}
            await asyncio.gather(auth.ensure_credentials(), auth.ensure_credentials())

        asyncio.run(contend())
        asyncio.run(contend())
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
