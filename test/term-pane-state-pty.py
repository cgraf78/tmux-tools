"""Verify terminal bytes and client lifetime without a live terminal or server."""

from __future__ import annotations

import base64
import json
import os
import selectors
import subprocess
import sys
import unittest
from pathlib import Path

COMMAND = sys.argv.pop(1)
FIXTURE = Path(sys.argv.pop(1))


class Publication(unittest.TestCase):
    """Observe the actual output descriptor rather than mock write calls."""

    def run_publication(self, term: str, changed: bool = False, route: int = 3) -> tuple:
        """Run one short-lived publisher with an invocation-owned pseudo tty."""
        master, slave = os.openpty()
        seen = FIXTURE / "seen"
        seen.unlink(missing_ok=True)
        tty = os.ttyname(slave)
        client = f"12 123 $7 0 {term} {tty} {tty}"
        env = dict(
            os.environ,
            STATE_CLIENTS=client,
            STATE_ROWS="%1 1 1 1",
            STATE_SEEN=str(seen),
            STATE_ROUTE_STATUS=str(route),
        )
        env.pop("STATE_SECOND_CLIENTS", None)
        if changed:
            env["STATE_SECOND_CLIENTS"] = client.replace("12 123", "13 124")
        try:
            result = subprocess.run(
                [
                    COMMAND,
                    "--socket",
                    "/private/test.sock",
                    "--client",
                    tty,
                    "--client-pid",
                    "12",
                    "--client-created",
                    "123",
                ],
                capture_output=True,
                env=env,
                timeout=5,
            )
            os.set_blocking(master, False)
            with selectors.DefaultSelector() as poll:
                poll.register(master, selectors.EVENT_READ)
                data = os.read(master, 65536) if poll.select(0.1) else b""
            return result, data
        finally:
            os.close(slave)
            os.close(master)
            seen.unlink(missing_ok=True)

    def test_raw_snapshot(self) -> None:
        """A direct client gets one structured OSC, with no rendered output."""
        result, data = self.run_publication("xterm-256color")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        prefix = b"\x1b]1337;SetUserVar=TERM_PANE_STATE="
        self.assertTrue(data.startswith(prefix), data)
        self.assertTrue(data.endswith(b"\x07"), data)
        payload = json.loads(base64.b64decode(data[len(prefix) : -1]))
        self.assertEqual(
            {key: payload[key] for key in ["v", "working", "pending", "failed"]},
            {"v": 1, "working": 1, "pending": 1, "failed": 1},
        )
        self.assertIsInstance(payload["heartbeat"], int)

    def test_immediate_tmux_frame(self) -> None:
        """A direct nested client uses exactly one tmux passthrough frame."""
        result, data = self.run_publication("tmux-256color")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(data.startswith(b"\x1bPtmux;\x1b\x1b]1337;"), data)
        self.assertTrue(data.endswith(b"\x07\x1b\\"), data)

    def test_client_replaced_after_snapshot(self) -> None:
        """A reused name cannot receive state after the original disappears."""
        result, data = self.run_publication("xterm-256color", changed=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(data, b"")

    def test_parent_routing_suppresses_direct_output(self) -> None:
        """A routed snapshot must not also leak raw escapes into a parent pane."""
        result, data = self.run_publication("xterm-256color", route=0)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data, b"")

    def test_route_failure_does_not_fall_back(self) -> None:
        """A failed hierarchical route cannot be replaced with unsafe tty output."""
        result, data = self.run_publication("xterm-256color", route=1)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(data, b"")


if __name__ == "__main__":
    unittest.main()
