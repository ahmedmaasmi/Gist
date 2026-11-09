# backend/app/provenance.py
"""Which code produced an output (PRD 10.3: every evaluation records its commit)."""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Only code and input data decide whether an output is reproducible from a commit. Regenerated reports
# are outputs, so changes to them must not mark the build as "-dirty".
TRACKED_INPUTS = ("backend", "data/templates", "data/names.json", "Makefile")


def git_commit() -> str:
    """Short commit hash, with "-dirty" if code or input data have uncommitted changes."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        changes = subprocess.run(
            ["git", "status", "--porcelain", "--", *TRACKED_INPUTS],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}-dirty" if changes else sha
