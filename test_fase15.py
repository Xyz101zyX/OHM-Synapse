import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).parent


class TestPyproject(unittest.TestCase):
    def test_pyproject_exists(self):
        p = HERE / "pyproject.toml"
        self.assertTrue(p.exists(), "pyproject.toml not found")

    def test_pyproject_is_valid_toml(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib not available")
        p = HERE / "pyproject.toml"
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        self.assertIn("project", data)
        self.assertEqual(data["project"]["name"], "ohm-synapse")
        self.assertIn("scripts", data["project"])
        self.assertIn("ohm", data["project"]["scripts"])

    def test_required_modules_listed(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib not available")
        data = tomllib.loads((HERE / "pyproject.toml").read_text(encoding="utf-8"))
        mods = data.get("tool", {}).get("setuptools", {}).get("py-modules", [])
        for m in ("ohm_synapse", "ohm_chat", "ohm_kairos", "ohm_cli"):
            self.assertIn(m, mods, f"module {m} not in py-modules")


class TestCLIImport(unittest.TestCase):
    def test_import(self):
        sys.path.insert(0, str(HERE))
        import importlib
        import ohm_cli
        self.assertTrue(hasattr(ohm_cli, "main"))
        self.assertTrue(hasattr(ohm_cli, "build_parser"))

    def test_parser_has_all_commands(self):
        sys.path.insert(0, str(HERE))
        import ohm_cli
        parser = ohm_cli.build_parser()
        sub_action = None
        for a in parser._actions:
            if hasattr(a, "choices") and a.choices:
                for choice in a.choices:
                    if choice in ("init", "run", "stop", "status", "chat",
                                  "broker", "two-peers", "list", "version"):
                        sub_action = True
        self.assertTrue(sub_action, "not all expected subcommands present")

    def test_version_command(self):
        sys.path.insert(0, str(HERE))
        import ohm_cli
        rc = ohm_cli.main(["version"])
        self.assertEqual(rc, 0)


class TestCLIInit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="ohm_test_home_"))
        self.old_env = os.environ.get("OHM_HOME")
        os.environ["OHM_HOME"] = str(self.tmpdir)
        sys.path.insert(0, str(HERE))
        import importlib
        import ohm_cli
        importlib.reload(ohm_cli)
        self.cli = ohm_cli

    def tearDown(self):
        if self.old_env is not None:
            os.environ["OHM_HOME"] = self.old_env
        else:
            os.environ.pop("OHM_HOME", None)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_dir(self):
        rc = self.cli.main(["init", "alice"])
        self.assertEqual(rc, 0)
        pdir = self.tmpdir / "peers" / "alice"
        self.assertTrue(pdir.exists())
        self.assertTrue((pdir / "config.json").exists())

    def test_init_config_json_is_valid(self):
        self.cli.main(["init", "alice"])
        pdir = self.tmpdir / "peers" / "alice"
        data = json.loads((pdir / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "alice")
        self.assertIn("created", data)
        self.assertIn("version", data)

    def test_init_refuses_overwrite(self):
        self.cli.main(["init", "alice"])
        rc = self.cli.main(["init", "alice"])
        self.assertNotEqual(rc, 0)

    def test_init_force_overwrites(self):
        self.cli.main(["init", "alice"])
        rc = self.cli.main(["init", "alice", "--force"])
        self.assertEqual(rc, 0)

    def test_init_rejects_bad_name(self):
        rc = self.cli.main(["init", "bad name!"])
        self.assertNotEqual(rc, 0)


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="ohm_reg_"))
        self.old_env = os.environ.get("OHM_HOME")
        os.environ["OHM_HOME"] = str(self.tmpdir)
        sys.path.insert(0, str(HERE))
        import importlib
        import ohm_cli
        importlib.reload(ohm_cli)
        self.cli = ohm_cli

    def tearDown(self):
        if self.old_env is not None:
            os.environ["OHM_HOME"] = self.old_env
        else:
            os.environ.pop("OHM_HOME", None)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_empty(self):
        reg = self.cli.load_registry()
        self.assertEqual(reg, {})

    def test_save_and_load(self):
        self.cli.save_registry({"x": {"port": 1, "pid": 2}})
        reg = self.cli.load_registry()
        self.assertEqual(reg["x"]["port"], 1)

    def test_list_empty(self):
        rc = self.cli.main(["list"])
        self.assertEqual(rc, 0)

    def test_list_with_entries(self):
        self.cli.save_registry({
            "a": {"port": 1, "pid": 1, "started": time.time()},
            "b": {"port": 2, "pid": 2, "started": time.time()},
        })
        rc = self.cli.main(["list"])
        self.assertEqual(rc, 0)

    def test_status_unknown(self):
        rc = self.cli.main(["status", "nope"])
        self.assertEqual(rc, 1)


class TestHelpers(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(HERE))
        import importlib
        import ohm_cli
        importlib.reload(ohm_cli)
        self.cli = ohm_cli

    def test_find_free_port(self):
        p = self.cli.find_free_port(50000, 50100)
        self.assertGreaterEqual(p, 50000)
        self.assertLess(p, 50100)

    def test_is_pid_alive_self(self):
        self.assertTrue(self.cli.is_pid_alive(os.getpid()))

    def test_is_pid_alive_nonsense(self):
        self.assertFalse(self.cli.is_pid_alive(-1))


class TestEndToEnd(unittest.TestCase):
    """Smoke test: start headless peer via CLI, ping, stop."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="ohm_e2e_cli_"))
        self.old_env = os.environ.get("OHM_HOME")
        os.environ["OHM_HOME"] = str(self.tmpdir)
        sys.path.insert(0, str(HERE))
        import importlib
        import ohm_cli
        importlib.reload(ohm_cli)
        self.cli = ohm_cli
        self.peer_proc = None

    def tearDown(self):
        if getattr(self, 'peer_proc', None) and self.peer_proc.poll() is None:
            try:
                self.peer_proc.send_signal(2)
                self.peer_proc.wait(timeout=6)
            except Exception:
                try:
                    self.peer_proc.kill()
                except Exception:
                    pass
        if self.old_env is not None:
            os.environ["OHM_HOME"] = self.old_env
        else:
            os.environ.pop("OHM_HOME", None)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_headless_peer_starts_and_responds(self):
        rc = self.cli.main(["init", "smoke"])
        self.assertEqual(rc, 0)

        port = self.cli.find_free_port(59000, 59100)

        env = os.environ.copy()
        env["OHM_HOME"] = str(self.tmpdir)
        env["OHM_TEST_MODE"] = "1"
        self.peer_proc = subprocess.Popen(
            [sys.executable, "-m", "run_peer",
             "--name", "smoke",
             "--port", str(port),
             "--data-dir", str(self.tmpdir / "peers" / "smoke"),
             "--headless"],
            cwd=str(HERE),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        ready = False
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.peer_proc.poll() is not None:
                out = self.peer_proc.stdout.read() if self.peer_proc.stdout else ""
                self.fail(f"peer exited early: {out}")
            if self.cli.http_get(port, "/ping", timeout=2):
                ready = True
                break
            time.sleep(0.5)

        self.assertTrue(ready, "peer did not become ready within 60s")

        st = self.cli.http_get(port, "/status")
        self.assertIsNotNone(st)
        self.assertIn("node_id", st)
        self.assertIn("mqtt", st)
        self.assertIsInstance(st.get("mqtt"), bool)

        r = self.cli.http_post(port, "/think", {"query": "/help"})
        self.assertIsNotNone(r)
        self.assertIn("status", r)
        self.assertEqual(r["status"], "HELP")


if __name__ == "__main__":
    unittest.main(verbosity=2)