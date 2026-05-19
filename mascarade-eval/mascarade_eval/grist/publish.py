# mascarade_eval/grist/publish.py
"""Publish an exported snapshot to its HuggingFace dataset repo."""
from __future__ import annotations

from pathlib import Path


def _hf_upload(*, path_or_fileobj, path_in_repo, repo_id, repo_type,
               commit_message):
    from huggingface_hub import upload_file
    upload_file(path_or_fileobj=path_or_fileobj, path_in_repo=path_in_repo,
                repo_id=repo_id, repo_type=repo_type,
                commit_message=commit_message)


def publish_snapshot(snapshot_path: str, hf_dataset_id: str,
                     filename: str, uploader=_hf_upload) -> None:
    """Upload one exported .jsonl snapshot to its HF dataset repo.

    `uploader` is injected for testing; production uses huggingface_hub.
    """
    path = Path(snapshot_path)
    if not path.exists():
        raise FileNotFoundError(f"snapshot not found: {snapshot_path}")
    uploader(
        path_or_fileobj=str(path),
        path_in_repo=filename,
        repo_id=hf_dataset_id,
        repo_type="dataset",
        commit_message=f"dataset: refresh {filename} from Grist export",
    )
