"""CLI contracts exercised from a directory outside the source tree."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "snooze_mcp", "--state", self.temp.name, *args],
            cwd=self.temp.name,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_schedule_process_and_read(self):
        added = self.run_cli("add", '{"title":"CLI test","delay_seconds":0}')
        self.assertEqual(added.returncode, 0, added.stderr)
        job_id = json.loads(added.stdout)["id"]
        processed = self.run_cli("worker", "--once")
        self.assertEqual(processed.returncode, 0, processed.stderr)
        result = self.run_cli("get", job_id)
        self.assertEqual(json.loads(result.stdout)["status"], "completed")
        self.assertEqual(len(json.loads(self.run_cli("events").stdout)), 1)

    def test_invalid_json_has_a_concise_error(self):
        for value in ("broken", "[]", '{"unexpected":true}'):
            result = self.run_cli("add", value)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_version_does_not_need_a_worker(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("0.1.0", result.stdout)

    def test_only_one_worker_can_run(self):
        worker = subprocess.Popen(
            [sys.executable, "-m", "snooze_mcp", "--state", self.temp.name, "worker"],
            cwd=self.temp.name,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            for _ in range(50):
                health = self.run_cli("health")
                if health.returncode == 0 and json.loads(health.stdout)["worker_recently_seen"]:
                    break
                time.sleep(0.02)
            else:
                self.fail("Worker did not become healthy")
            duplicate = self.run_cli("worker", "--once")
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("already running", duplicate.stderr)
        finally:
            worker.terminate()
            worker.wait(timeout=5)
            worker.stderr.close()

    def test_environment_selects_state_directory(self):
        result = subprocess.run(
            [sys.executable, "-m", "snooze_mcp", "health"],
            cwd=self.temp.name,
            env={**os.environ, "SNOOZE_STATE": self.temp.name},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state_dir"], os.path.realpath(self.temp.name))
