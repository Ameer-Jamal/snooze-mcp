import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from snooze_mcp.core import MAX_SLEEP, MIN_SLEEP, Scheduler, delivery_argv, run_command
from snooze_mcp.server import with_worker_warning

THREAD = "00000000-0000-0000-0000-000000000001"


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scheduler = Scheduler(self.temp.name)
        codex = patch("snooze_mcp.core.shutil.which", return_value="/test/bin/codex")
        codex.start()
        self.addCleanup(codex.stop)

    def add(self, **kwargs):
        kwargs.setdefault("cwd", self.temp.name)
        return self.scheduler.schedule("test", delay_seconds=0, **kwargs)

    def test_timer_survives_restart_and_only_completes_once(self):
        job = self.add()
        restarted = Scheduler(self.temp.name)
        restarted.tick()
        restarted.tick()
        self.assertEqual(restarted.get(job["id"])["status"], "completed")
        self.assertEqual(len(restarted.events()), 1)
        self.assertEqual(restarted.events()[0]["delivery"], "inbox")

    def test_pending_file_does_not_wake_ai_and_backs_off(self):
        target = Path(self.temp.name) / "done"
        job = self.add(
            kind="file",
            path=str(target),
            interval_seconds=10,
            max_interval_seconds=40,
            thread_id="00000000-0000-0000-0000-000000000001",
        )
        with patch("snooze_mcp.core.run_command") as wake:
            self.scheduler.tick()
            self.assertEqual(self.scheduler.events(), [])
            wake.assert_not_called()
            now = time.time()
            self.scheduler.tick(now + 11)
            self.assertGreaterEqual(self.scheduler.get(job["id"])["next_at"], now + 19)
            target.touch()
            wake.return_value = (0, "accepted")
            self.scheduler.tick(now + 50)
            self.scheduler.tick(now + 51)
            self.assertEqual(wake.call_count, 1)
            self.assertIn("queue", wake.call_args.args[0])
        self.assertEqual(self.scheduler.events()[0]["delivery"], "queued")

    def test_command_exit_codes_and_three_error_limit(self):
        job = self.add(
            kind="command", argv=[sys.executable, "-c", "raise SystemExit(1)"], interval_seconds=1
        )
        self.scheduler.tick()
        self.assertEqual(self.scheduler.get(job["id"])["status"], "active")
        self.assertEqual(self.scheduler.events(), [])
        with patch("snooze_mcp.core.run_command", return_value=(2, "broken")):
            for offset in (10, 20, 30):
                self.scheduler.tick(time.time() + offset)
        self.assertEqual(self.scheduler.get(job["id"])["status"], "failed")

    def test_command_completion(self):
        job = self.add(kind="command", argv=[sys.executable, "-c", "print('ready')"])
        self.scheduler.tick()
        self.assertEqual(self.scheduler.get(job["id"])["status"], "completed")
        self.assertIn("ready", self.scheduler.events()[0]["detail"])

    def test_cancel_and_expiry(self):
        cancelled = self.add()
        self.scheduler.cancel(cancelled["id"])
        expired = self.add(expires_in_seconds=2)
        self.scheduler.tick(time.time() + 5)
        self.assertEqual(self.scheduler.get(cancelled["id"])["status"], "cancelled")
        self.assertEqual(self.scheduler.get(expired["id"])["status"], "expired")
        self.assertEqual(len(self.scheduler.events()), 1)

    def test_timeout_kills_probe(self):
        with self.assertRaises(TimeoutError):
            run_command([sys.executable, "-c", "import time; time.sleep(10)"], self.temp.name, 0.1)

    def test_delivery_failure_does_not_repeat_model_attempt(self):
        self.add(thread_id="00000000-0000-0000-0000-000000000001")
        with patch("snooze_mcp.core.run_command", return_value=(1, "offline")) as wake:
            self.scheduler.tick()
            self.scheduler.tick()
            self.assertEqual(wake.call_count, 1)
        self.assertEqual(self.scheduler.events()[0]["delivery"], "failed")

    def test_missing_codex_is_a_failed_delivery_without_a_process(self):
        self.add(thread_id="00000000-0000-0000-0000-000000000001")
        with (
            patch("snooze_mcp.core.shutil.which", return_value=None),
            patch.dict(os.environ, {"SNOOZE_CODEX": ""}),
            patch("snooze_mcp.core.run_command") as wake,
        ):
            self.scheduler.tick()
            wake.assert_not_called()
        self.assertEqual(self.scheduler.events()[0]["delivery"], "failed")

    def test_delivery_timeout_is_unknown_and_not_retried(self):
        self.add(thread_id="00000000-0000-0000-0000-000000000001")
        with patch("snooze_mcp.core.run_command", side_effect=TimeoutError("deadline")) as wake:
            self.scheduler.tick()
            self.scheduler.tick()
            self.assertEqual(wake.call_count, 1)
        self.assertEqual(self.scheduler.events()[0]["delivery"], "unknown")

    def test_reject_invalid_schedules(self):
        for kwargs in (
            {"interval_seconds": 0},
            {"delay_seconds": float("nan")},
            {"thread_id": "--last"},
            {"kind": "file", "path": "relative"},
            {"kind": "command", "argv": ["echo", "hi"]},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.scheduler.schedule("test", **kwargs)

    def test_output_is_bounded(self):
        code, output = run_command([sys.executable, "-c", "print('x' * 10000)"], self.temp.name, 5)
        self.assertEqual(code, 0)
        self.assertLess(len(output), 4200)
        self.assertTrue(output.endswith("[output truncated]"))

    def test_runaway_output_is_terminated(self):
        with self.assertRaisesRegex(RuntimeError, "exceeded"):
            run_command(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 2000000)"],
                self.temp.name,
                5,
            )

    def test_command_arguments_are_not_shell_interpolated(self):
        literal = "$(touch should-not-exist); echo unsafe"
        code, output = run_command(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", literal], self.temp.name, 5
        )
        self.assertEqual(code, 0)
        self.assertIn(literal, output)
        self.assertFalse((Path(self.temp.name) / "should-not-exist").exists())

    def test_missing_executable_becomes_failure_after_retries(self):
        job = self.add(kind="command", argv=["/does/not/exist"], interval_seconds=1)
        for offset in (0, 10, 20):
            self.scheduler.tick(time.time() + offset)
        self.assertEqual(self.scheduler.get(job["id"])["status"], "failed")

    def test_command_requires_explicit_working_directory(self):
        with self.assertRaisesRegex(ValueError, "explicit cwd"):
            self.scheduler.schedule("test", kind="command", argv=[sys.executable])

    def test_cancel_during_probe_does_not_emit_completion(self):
        job = self.add(kind="command", argv=[sys.executable, "-c", "pass"])

        def probe(*args):
            self.scheduler.cancel(job["id"])
            return 0, "done"

        with patch("snooze_mcp.core.run_command", side_effect=probe):
            self.scheduler.tick()
        self.assertEqual(self.scheduler.get(job["id"])["status"], "cancelled")
        self.assertEqual(self.scheduler.events(), [])

    def test_cancel_after_snapshot_skips_later_probe(self):
        self.add(kind="command", argv=[sys.executable, "-c", "pass"])
        second = self.add(kind="command", argv=[sys.executable, "-c", "pass"])

        def probe(*args):
            self.scheduler.cancel(second["id"])
            return 0, "done"

        with patch("snooze_mcp.core.run_command", side_effect=probe) as run:
            self.scheduler.tick()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(self.scheduler.get(second["id"])["status"], "cancelled")

    def test_pagination_and_active_job_order(self):
        for _ in range(3):
            self.add()
        self.scheduler.tick()
        active = self.add()
        self.assertEqual(self.scheduler.jobs(limit=1)[0]["id"], active["id"])
        page1 = self.scheduler.events(limit=2)
        page2 = self.scheduler.events(limit=2, offset=2)
        self.assertEqual(len(page1) + len(page2), 3)
        self.assertGreater(page1[-1]["id"], page2[0]["id"])
        with self.assertRaises(ValueError):
            self.scheduler.events(limit=101)

    def test_error_count_resets_after_pending_result(self):
        job = self.add(kind="command", argv=[sys.executable], interval_seconds=1)
        with patch(
            "snooze_mcp.core.run_command", side_effect=[(2, "error"), (1, "pending"), (2, "error")]
        ):
            for offset in (0, 10, 20):
                self.scheduler.tick(time.time() + offset)
        self.assertEqual(self.scheduler.get(job["id"])["errors"], 1)
        self.assertEqual(self.scheduler.get(job["id"])["status"], "active")

    def test_interrupted_delivery_is_not_retried(self):
        self.add(thread_id="00000000-0000-0000-0000-000000000001")
        with patch.object(self.scheduler, "deliver"):
            self.scheduler.tick()
        with self.scheduler.db() as db:
            db.execute("UPDATE events SET delivery='sending'")
        with patch("snooze_mcp.core.run_command") as wake:
            self.scheduler.worker(once=True)
            wake.assert_not_called()
        self.assertEqual(self.scheduler.events()[0]["delivery"], "unknown")

    def deliver_with(self, **env):
        self.add(thread_id=THREAD)
        with (
            patch.dict(os.environ, env),
            patch("snooze_mcp.core.run_command", return_value=(0, "ok")) as wake,
        ):
            self.scheduler.tick()
        return wake

    def test_custom_delivery_command_replaces_codex(self):
        wake = self.deliver_with(SNOOZE_DELIVERY_COMMAND="/bin/agent --to {thread} -m {message}")
        argv = wake.call_args.args[0]
        self.assertEqual(argv[:3], ["/bin/agent", "--to", THREAD])
        self.assertEqual(argv[3], "-m")
        self.assertIn("Snooze scheduler: test [completed]", argv[4])
        self.assertEqual(len(argv), 5)
        self.assertEqual(self.scheduler.events()[0]["delivery"], "queued")

    def test_blank_delivery_command_uses_codex(self):
        wake = self.deliver_with(SNOOZE_DELIVERY_COMMAND="  ", SNOOZE_CODEX="/x/codex")
        self.assertEqual(wake.call_args.args[0][:2], ["/x/codex", "queue"])

    def test_placeholders_cannot_inject_arguments_or_expand_twice(self):
        message = "a b; rm -rf / {thread} $(x) 'q' {message}"
        argv = delivery_argv("/bin/agent {thread} --msg={message} '{message}'", THREAD, message)
        self.assertEqual(argv, ["/bin/agent", THREAD, f"--msg={message}", message])

    def test_invalid_delivery_templates_are_rejected(self):
        for template in ("", "   ", "{message} {thread}", "'unterminated"):
            with self.subTest(template=template), self.assertRaises(ValueError):
                delivery_argv(template, THREAD, "m")

    def test_bad_delivery_template_is_failed_without_a_process(self):
        for template in ("'unterminated", "{message}"):
            with self.subTest(template=template):
                self.add(thread_id=THREAD)
                wake = self.deliver_with(SNOOZE_DELIVERY_COMMAND=template)
                wake.assert_not_called()
        self.assertEqual({e["delivery"] for e in self.scheduler.events()}, {"failed"})

    def test_custom_delivery_failure_and_timeout_states(self):
        for outcome, state in (((1, "no"), "failed"), (TimeoutError("late"), "unknown")):
            self.add(thread_id=THREAD)
            mock = {"side_effect": outcome}
            with (
                patch.dict(os.environ, {"SNOOZE_DELIVERY_COMMAND": "/bin/agent {message}"}),
                patch("snooze_mcp.core.run_command", **mock) as wake,
            ):
                self.scheduler.tick()
                self.scheduler.tick()
                self.assertEqual(wake.call_count, 1)
            self.assertEqual(self.scheduler.events()[0]["delivery"], state)

    def event_with(self, delivery, thread_id=THREAD):
        self.add(thread_id=thread_id)
        with patch.object(self.scheduler, "deliver"):
            self.scheduler.tick()
        event_id = self.scheduler.events()[0]["id"]
        with self.scheduler.db() as db:
            db.execute("UPDATE events SET delivery=? WHERE id=?", (delivery, event_id))
        return event_id

    def test_retry_failed_and_unknown_deliveries(self):
        for state in ("failed", "unknown"):
            event_id = self.event_with(state)
            with patch("snooze_mcp.core.run_command", return_value=(0, "ok")) as wake:
                result = self.scheduler.retry_delivery(event_id)
            self.assertEqual(wake.call_count, 1)
            self.assertEqual(result["delivery"], "queued")
            self.assertEqual(result["delivery_detail"], "ok")

    def test_retry_that_fails_again_stays_failed_and_is_single_attempt(self):
        event_id = self.event_with("failed")
        with patch("snooze_mcp.core.run_command", return_value=(1, "still down")) as wake:
            self.assertEqual(self.scheduler.retry_delivery(event_id)["delivery"], "failed")
            self.scheduler.tick()
            self.assertEqual(wake.call_count, 1)

    def test_retry_timeout_becomes_unknown(self):
        event_id = self.event_with("failed")
        with patch("snooze_mcp.core.run_command", side_effect=TimeoutError("late")):
            self.assertEqual(self.scheduler.retry_delivery(event_id)["delivery"], "unknown")

    def test_retry_is_refused_for_other_states_and_bad_ids(self):
        for state in ("queued", "pending", "sending", "inbox"):
            event_id = self.event_with(state)
            with (
                patch("snooze_mcp.core.run_command") as wake,
                self.assertRaises(ValueError),
            ):
                self.scheduler.retry_delivery(event_id)
            wake.assert_not_called()
            self.assertEqual(self.scheduler.events()[0]["delivery"], state)
        for bad in (9999, "1", True, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.scheduler.retry_delivery(bad)

    def test_retry_is_refused_without_a_thread(self):
        event_id = self.event_with("failed", thread_id=None)
        with patch("snooze_mcp.core.run_command") as wake, self.assertRaises(ValueError):
            self.scheduler.retry_delivery(event_id)
        wake.assert_not_called()

    def test_concurrent_retry_claims_once(self):
        event_id = self.event_with("failed")
        with self.scheduler.db() as db:
            db.execute("UPDATE events SET delivery='sending' WHERE id=?", (event_id,))
        self.assertFalse(self.scheduler._send(event_id, "failed"))

    def test_sleep_targets_earliest_job_with_bounds(self):
        now = time.time()
        self.assertEqual(self.scheduler.sleep_seconds(now), MAX_SLEEP)
        self.scheduler.schedule("far", delay_seconds=3600, cwd=self.temp.name)
        self.assertEqual(self.scheduler.sleep_seconds(), MAX_SLEEP)
        self.scheduler.schedule("soon", delay_seconds=2, cwd=self.temp.name)
        self.assertTrue(MIN_SLEEP < self.scheduler.sleep_seconds() <= 2)
        self.scheduler.schedule("due", delay_seconds=0, cwd=self.temp.name)
        self.assertEqual(self.scheduler.sleep_seconds(now + 10), MIN_SLEEP)

    def test_sleep_considers_expiry(self):
        self.scheduler.schedule(
            "expiring",
            delay_seconds=0,
            interval_seconds=3000,
            expires_in_seconds=2,
            cwd=self.temp.name,
        )
        with self.scheduler.db() as db:
            db.execute("UPDATE jobs SET next_at=next_at+3000")
        self.assertTrue(self.scheduler.sleep_seconds() <= 2)

    def test_worker_sleeps_using_computed_delay(self):
        with (
            patch.object(self.scheduler, "sleep_seconds", return_value=0.25),
            patch("snooze_mcp.core.time.sleep", side_effect=KeyboardInterrupt) as nap,
            self.assertRaises(KeyboardInterrupt),
        ):
            self.scheduler.worker()
        nap.assert_called_once_with(0.25)

    def test_schedule_warns_when_worker_is_not_running(self):
        job = with_worker_warning(self.scheduler, self.add())
        self.assertIn("Worker is not running", job["warning"])

    def test_schedule_has_no_warning_when_worker_is_running(self):
        job = self.add()
        with patch.object(self.scheduler, "health", return_value={"worker_running": True}):
            self.assertNotIn("warning", with_worker_warning(self.scheduler, job))

    def test_database_is_private(self):
        self.assertEqual((Path(self.temp.name) / "snooze.db").stat().st_mode & 0o777, 0o600)

    def test_health_does_not_report_stopped_worker_as_running(self):
        self.scheduler.worker(once=True)
        self.assertFalse(self.scheduler.health()["worker_running"])
        self.assertFalse(self.scheduler.health()["worker_recently_seen"])

    def test_invalid_metadata_is_rejected(self):
        for kwargs in (
            {"title": " "},
            {"title": "x" * 257},
            {"instruction": None},
            {"interval_seconds": True},
            {"expires_in_seconds": float("inf")},
            {"timeout_seconds": 301},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.scheduler.schedule(**({"title": "test"} | kwargs))

    def test_real_stdio_mcp(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def check():
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "snooze_mcp", "--state", self.temp.name, "serve"],
            )
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    self.assertIn("schedule_check", names)
                    self.assertIn("retry_delivery", names)
                    result = await session.call_tool(
                        "schedule_check", {"title": "MCP smoke", "delay_seconds": 0}
                    )
                    self.assertFalse(result.isError, result)
                    self.assertIn("warning", result.content[0].text)
                    refused = await session.call_tool("retry_delivery", {"event_id": 999})
                    self.assertTrue(refused.isError)
                    self.scheduler.worker(once=True)
                    events = await session.call_tool("read_events", {})
                    self.assertFalse(events.isError)
                    self.assertIn("completed", str(events))
                    result = await session.call_tool("schedule_check", {"title": "Cancel me"})
                    self.assertFalse(result.isError)
                    job = json.loads(result.content[0].text)
                    cancelled = await session.call_tool("cancel_job", {"job_id": job["id"]})
                    self.assertIn("true", cancelled.content[0].text)

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
