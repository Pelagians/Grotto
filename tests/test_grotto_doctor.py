#!/usr/bin/python3
"""Regression tests for non-invasive grotto-doctor sandbox diagnostics."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock


DEFAULT_DOCTOR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "runtimes/chatgpt-desktop/root/usr/local/bin/grotto-doctor"
)
DOCTOR_PATH = pathlib.Path(
    os.environ.get("GROTTO_DOCTOR_UNDER_TEST", str(DEFAULT_DOCTOR))
)
LOADER = importlib.machinery.SourceFileLoader("grotto_doctor_under_test", str(DOCTOR_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
doctor = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(doctor)


def check(ok: bool = True, stderr: str = "") -> dict[str, object]:
    return {
        "ok": ok,
        "returncode": 0 if ok else 1,
        "stdout": "",
        "stderr": stderr,
    }


def probe_record() -> dict[str, object]:
    checks = {
        "direct_command": check(),
        "bubblewrap_fresh_dev": check(),
        "bubblewrap_protected_child_remount": check(),
        "codex_workspace_permissions": check(),
        "landlock_workspace_profile": check(),
    }
    return {
        "schema_version": doctor.PROBE_CACHE_SCHEMA_VERSION,
        "status": "completed",
        "reason": None,
        "active_probe": True,
        "may_generate_host_avcs": True,
        "probe_started_at": "2026-07-17T20:00:00Z",
        "probe_completed_at": "2026-07-17T20:00:01Z",
        "selected_backend": "bubblewrap",
        "selected_bwrap": "/fake/bwrap",
        "ok": True,
        "checks": checks,
        "details": {"matrix_runs": 1},
    }


class DoctorTest(unittest.TestCase):
    def static_environment(self, stack: ExitStack) -> list[list[str]]:
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> dict[str, object]:
            commands.append(command)
            return check()

        stack.enter_context(mock.patch.object(doctor, "run", side_effect=fake_run))
        stack.enter_context(mock.patch.object(doctor, "resolve_bundled_bwrap", return_value=None))
        stack.enter_context(
            mock.patch.object(
                doctor.shutil,
                "which",
                side_effect=lambda name, path=None: "/fake/bwrap" if name == "bwrap" else None,
            )
        )
        stack.enter_context(
            mock.patch.object(
                doctor,
                "effective_landlock_enabled",
                return_value=(False, check()),
            )
        )
        stack.enter_context(
            mock.patch.object(
                doctor,
                "version_info",
                side_effect=lambda path, args: {"path": path, "version": None},
            )
        )
        stack.enter_context(mock.patch.object(doctor, "mount_entry", return_value={"ok": True}))
        stack.enter_context(mock.patch.object(doctor, "device_inventory", return_value=[]))
        stack.enter_context(mock.patch.object(doctor, "memory_status", return_value={}))
        stack.enter_context(
            mock.patch.object(
                doctor,
                "network_status",
                return_value={
                    "host": doctor.AUTH_HOST,
                    "dns": {"ok": None},
                    "https": {"ok": None},
                },
            )
        )
        stack.enter_context(
            mock.patch.object(doctor, "probe_cache_path", return_value=pathlib.Path("/tmp/cache.json"))
        )
        stack.enter_context(mock.patch.object(doctor, "read_probe_cache", return_value=(None, None)))
        stack.enter_context(mock.patch.object(doctor, "write_probe_cache", return_value=None))
        return commands

    def test_default_collect_does_not_invoke_bwrap(self) -> None:
        with ExitStack() as stack:
            commands = self.static_environment(stack)
            probe = stack.enter_context(mock.patch.object(doctor, "run_sandbox_probe"))
            report = doctor.collect()

        probe.assert_not_called()
        self.assertFalse(report["active_probe"])
        self.assertEqual(report["sandbox_probe"]["status"], "not_run")
        self.assertEqual(report["sandbox_probe"]["reason"], doctor.PROBE_NOT_RUN_REASON)
        self.assertEqual(report["checks"], {})
        self.assertFalse(
            any(pathlib.Path(command[0]).name == "bwrap" for command in commands)
        )

    def test_json_changes_only_output_formatting(self) -> None:
        report = {
            "ok": None,
            "active_probe": False,
            "sandbox_probe": {
                "status": "not_run",
                "reason": doctor.PROBE_NOT_RUN_REASON,
            },
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(doctor, "collect", return_value=report) as collect,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            returncode = doctor.main(["--json"])

        self.assertEqual(returncode, 0)
        collect.assert_called_once_with(active_probe=False)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        self.assertEqual(stderr.getvalue(), "")

    def test_only_probe_option_invokes_active_probe(self) -> None:
        with ExitStack() as stack:
            self.static_environment(stack)
            probe = stack.enter_context(
                mock.patch.object(doctor, "run_sandbox_probe", return_value=probe_record())
            )
            doctor.collect(active_probe=False)
            report = doctor.collect(active_probe=True)

        probe.assert_called_once_with("/fake/bwrap", "bubblewrap")
        self.assertTrue(report["active_probe"])
        self.assertEqual(report["sandbox_probe"]["status"], "completed")
        self.assertEqual(report["probe_started_at"], "2026-07-17T20:00:00Z")
        self.assertEqual(report["probe_completed_at"], "2026-07-17T20:00:01Z")

    def test_human_and_json_rendering_reuse_one_probe_result(self) -> None:
        with ExitStack() as stack:
            self.static_environment(stack)
            probe = stack.enter_context(
                mock.patch.object(doctor, "run_sandbox_probe", return_value=probe_record())
            )
            report = doctor.collect(active_probe=True)
            human = doctor.render_human(report)
            machine = json.dumps(report, sort_keys=True)

        probe.assert_called_once()
        self.assertIn("2026-07-17T20:00:00Z", human)
        self.assertIn("2026-07-17T20:00:01Z", human)
        self.assertIn("2026-07-17T20:00:00Z", machine)
        self.assertIn("2026-07-17T20:00:01Z", machine)

    def test_explicit_probe_prints_avc_warning(self) -> None:
        report = probe_record()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(doctor, "collect", return_value=report) as collect,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            returncode = doctor.main(["--probe-sandbox", "--json"])

        self.assertEqual(returncode, 0)
        collect.assert_called_once_with(active_probe=True)
        self.assertIn(
            "will intentionally trigger host SELinux AVCs",
            stderr.getvalue(),
        )
        self.assertTrue(json.loads(stdout.getvalue())["active_probe"])

    def test_probe_cache_round_trips_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "nested" / "probe.json"
            record = probe_record()
            self.assertIsNone(doctor.write_probe_cache(path, record))
            cached, error = doctor.read_probe_cache(path)

            self.assertIsNone(error)
            self.assertEqual(cached, record)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_unreadable_probe_cache_is_reported_without_crashing(self) -> None:
        path = mock.Mock()
        path.exists.side_effect = PermissionError("cache is not traversable")

        cached, error = doctor.read_probe_cache(path)

        self.assertIsNone(cached)
        self.assertIn("cache is not traversable", error)


if __name__ == "__main__":
    unittest.main()
