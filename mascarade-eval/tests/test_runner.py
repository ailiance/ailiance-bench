from unittest.mock import patch, MagicMock
import json, io
from mascarade_eval.runner import chat_completion


def test_chat_completion_extracts_content():
    fake = io.BytesIO(json.dumps(
        {"choices": [{"message": {"content": "the answer"}}]}).encode())
    fake.__enter__ = lambda s: s
    fake.__exit__ = lambda *a: None
    with patch("urllib.request.urlopen", return_value=fake):
        out = chat_completion("http://x/v1/chat/completions", "m", "prompt")
    assert out == "the answer"
