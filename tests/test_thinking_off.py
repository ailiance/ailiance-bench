"""Smoke test: lock the Qwen3.x `enable_thinking=False` fix in `generate_safe`.

Regression guard for commit c88d1cb. Without this kwarg, scorers silently
return 0/N on Qwen3.x because the assistant emits `<thinking>...</thinking>`
prefixes that confuse keyword-rate detectors.

Pure stdlib + unittest.mock — no MLX runtime required, so it can run on CI
where MLX is unavailable.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "bench_eu_kiki_v2.py"


def _load_generate_safe():
    """Load generate_safe with mlx and mlx_lm stubbed out (no MLX runtime needed)."""
    mlx = types.ModuleType("mlx")
    mlx.__path__ = []  # mark as package so `import mlx.core` works
    mlx_core = types.ModuleType("mlx.core")
    mlx_core.random = MagicMock()
    mlx_nn = types.ModuleType("mlx.nn")
    mlx.core = mlx_core
    mlx.nn = mlx_nn

    mlx_lm = types.ModuleType("mlx_lm")
    mlx_lm.__path__ = []
    mlx_lm.generate = MagicMock(return_value="ok")
    mlx_lm.load = MagicMock()

    sys.modules["mlx"] = mlx
    sys.modules["mlx.core"] = mlx_core
    sys.modules["mlx.nn"] = mlx_nn
    sys.modules["mlx_lm"] = mlx_lm

    spec = importlib.util.spec_from_file_location("bench_eu_kiki_v2", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_safe_passes_enable_thinking_false():
    module = _load_generate_safe()
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = "<formatted>"

    module.generate_safe(model=MagicMock(), tokenizer=tokenizer, prompt="hello")

    assert tokenizer.apply_chat_template.called
    kwargs = tokenizer.apply_chat_template.call_args.kwargs
    assert kwargs.get("enable_thinking") is False, (
        "Qwen3.x trap regression: enable_thinking must be False in generate_safe"
    )
    assert kwargs.get("add_generation_prompt") is True
    assert kwargs.get("tokenize") is False


def test_generate_safe_falls_back_when_kwarg_unsupported():
    """Older tokenizers raise TypeError on enable_thinking — we must retry without it."""
    module = _load_generate_safe()
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.side_effect = [
        TypeError("unexpected keyword argument 'enable_thinking'"),
        "<formatted>",
    ]

    module.generate_safe(model=MagicMock(), tokenizer=tokenizer, prompt="hello")

    assert tokenizer.apply_chat_template.call_count == 2
    second_kwargs = tokenizer.apply_chat_template.call_args_list[1].kwargs
    assert "enable_thinking" not in second_kwargs


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
