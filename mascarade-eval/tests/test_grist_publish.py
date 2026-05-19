# tests/test_grist_publish.py
import pytest
from mascarade_eval.grist.publish import publish_snapshot


def test_publish_snapshot_uploads_with_expected_args(tmp_path):
    snap = tmp_path / "kicad.20260519T120000Z.jsonl"
    snap.write_text('{"messages": []}\n')
    calls = []

    def fake_upload(*, path_or_fileobj, path_in_repo, repo_id, repo_type,
                    commit_message):
        calls.append({
            "path_or_fileobj": path_or_fileobj,
            "path_in_repo": path_in_repo,
            "repo_id": repo_id,
            "repo_type": repo_type,
            "commit_message": commit_message,
        })

    publish_snapshot(str(snap), "Ailiance-fr/mascarade-kicad-dataset",
                     "kicad_chat.jsonl", uploader=fake_upload)
    assert len(calls) == 1
    assert calls[0]["repo_id"] == "Ailiance-fr/mascarade-kicad-dataset"
    assert calls[0]["repo_type"] == "dataset"
    assert calls[0]["path_in_repo"] == "kicad_chat.jsonl"
    assert calls[0]["path_or_fileobj"] == str(snap)


def test_publish_snapshot_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        publish_snapshot(str(tmp_path / "nope.jsonl"),
                         "Ailiance-fr/mascarade-kicad-dataset",
                         "kicad_chat.jsonl", uploader=lambda **k: None)
