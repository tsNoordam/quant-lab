"""MLflow helpers: tracking setup, provenance tags and param flattening.

Provenance is what makes a run reproducible: the git commit (and whether the tree
was dirty) identifies the code, the DVC-locked md5 of the input panel identifies
the data.
"""

import hashlib
import os
import subprocess
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow  # noqa: E402
import yaml  # noqa: E402


def git_state(root: Path) -> dict[str, str]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        return {
            "git_commit": git("rev-parse", "HEAD"),
            "git_dirty": str(bool(git("status", "--porcelain"))).lower(),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "unknown", "git_dirty": "unknown"}


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dvc_locked_md5(root: Path, rel_path: str) -> str | None:
    """md5 recorded in dvc.lock for an output path, or None if it is not a stage output."""
    lock = root / "dvc.lock"
    if not lock.exists():
        return None
    stages = (yaml.safe_load(lock.read_text()) or {}).get("stages", {})
    for stage in stages.values():
        for out in stage.get("outs", []):
            if out.get("path") == rel_path:
                return out.get("md5")
    return None


def data_provenance(root: Path, rel_path: str) -> dict[str, str]:
    actual = file_md5(root / rel_path)
    locked = dvc_locked_md5(root, rel_path)
    return {
        "data_path": rel_path,
        "data_md5": actual,
        "data_dvc_lock_md5": locked or "none",
        "data_matches_dvc_lock": str(actual == locked).lower(),
    }


def flatten(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in d.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{name}."))
        else:
            out[name] = str(value)
    return out


def set_experiment(tracking_uri: str, experiment: str, artifact_root: Path) -> str:
    mlflow.set_tracking_uri(tracking_uri)
    existing = mlflow.get_experiment_by_name(experiment)
    if existing is not None:
        mlflow.set_experiment(experiment)
        return existing.experiment_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    experiment_id = mlflow.create_experiment(
        experiment, artifact_location=(artifact_root.resolve() / experiment).as_uri()
    )
    mlflow.set_experiment(experiment)
    return experiment_id
