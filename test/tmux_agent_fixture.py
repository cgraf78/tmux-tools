"""Shared helpers for private tmux agent-picker fixtures."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path


def copy_bash(target: Path, env: Mapping[str, str]) -> None:
    """Copy a bash that runs as the stand-in agent under the fixture environment.

    The copy gives the pane the agent's process name. Copy only the contents
    and mode because macOS refuses to copy the system bash's protected flags.
    Try the fixture's PATH in order, with /bin/bash as a fallback.
    """
    candidates = [
        str(Path(directory) / "bash")
        for directory in env.get("PATH", "").split(os.pathsep)
        if directory and os.access(Path(directory) / "bash", os.X_OK)
    ]
    for source in dict.fromkeys(candidates + ["/bin/bash"]):
        if not os.access(source, os.X_OK):
            continue
        shutil.copyfile(source, target)
        target.chmod(0o755)
        try:
            ran = subprocess.run([str(target), "-c", ":"], env=env, timeout=10, check=False)
        except OSError:
            continue
        if ran.returncode == 0:
            return
    raise SystemExit(f"FAIL: no copy of bash runs as a stand-in agent from {target.parent}")
