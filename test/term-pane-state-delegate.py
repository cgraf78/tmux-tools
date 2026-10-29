"""Verify the shell delegates all terminal delivery to the native owner."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

COMMAND = sys.argv.pop(1)
FIXTURE = Path(sys.argv.pop(1))


class Publication(unittest.TestCase):
    """The provider supplies counts and exact identity, never terminal bytes."""

    def run_publication(self, route: int) -> subprocess.CompletedProcess[bytes]:
        """Use the existing tmux/native fixtures without a real tty or server."""
        env = dict(
            os.environ,
            STATE_CLIENTS="12 123 $7 0 xterm-256color /dev/null /dev/null",
            STATE_ROWS="%1 1 1 1",
            STATE_ROUTE_STATUS=str(route),
        )
        env.pop("STATE_SEEN", None)
        env.pop("STATE_SECOND_CLIENTS", None)
        return subprocess.run(
            [
                COMMAND,
                "--socket",
                "/private/test.sock",
                "--client",
                "/dev/null",
                "--client-pid",
                "12",
                "--client-created",
                "123",
            ],
            capture_output=True,
            env=env,
            timeout=3,
            check=False,
        )

    def test_native_owner_success_is_silent(self) -> None:
        """Native success includes both direct and hierarchical publication."""
        result = self.run_publication(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        arguments = (FIXTURE / "native-args").read_text().splitlines()
        self.assertEqual(
            arguments,
            [
                "tmux",
                "attention",
                "--tmux-socket",
                "/private/test.sock",
                "--client-name",
                "/dev/null",
                "--client-pid",
                "12",
                "--client-created",
                "123",
                "--working",
                "1",
                "--pending",
                "1",
                "--failed",
                "1",
            ],
        )

    def test_native_failure_does_not_fall_back(self) -> None:
        """Failed admission or a timed-out tty write remains failure."""
        result = self.run_publication(1)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")

    def test_legacy_direct_result_fails_closed(self) -> None:
        """An old native helper cannot authorize an unbounded shell tty write."""
        result = self.run_publication(3)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
