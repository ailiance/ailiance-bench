# mlx-lm 0.31.3 — Gemma 4 quantized load fails on KV-shared layers

**Status (2026-05-11)** : fix already **merged upstream** in `ml-explore/mlx-lm`
([PR #1240](https://github.com/ml-explore/mlx-lm/pull/1240), merged
2026-05-04). The fix has **not yet been released on PyPI** — `mlx-lm==0.31.3`
(latest available on PyPI as of today) ships **without** the fix. Any machine
installing `mlx-lm` via `pip`/`uv pip` will hit the bug until the next release.

## Symptoms

```bash
python -m mlx_lm generate \
    --model lmstudio-community/gemma-4-E4B-it-MLX-4bit \
    --prompt "hello"
```

```
File ".../mlx_lm/utils.py", line 415, in load_model
    model.load_weights(list(weights.items()), strict=strict)
File ".../mlx/nn/layers/base.py", line 185, in load_weights
    raise ValueError(
ValueError: Received 126 parameters not in model:
language_model.model.layers.24.self_attn.k_norm.weight,
language_model.model.layers.24.self_attn.k_proj.biases,
language_model.model.layers.24.self_attn.k_proj.scales,
language_model.model.layers.24.self_attn.k_proj.weight,
language_model.model.layers.24.self_attn.v_proj.biases,
...
language_model.model.layers.31.self_attn.v_proj.weight.
```

Affects every quantized Gemma 4 checkpoint that ships KV-shared layer
projections in its safetensors (E2B, E4B, OptiQ variants, etc.).

## Root cause — Gemma 4 KV-shared layers

Gemma 4 introduces **KV-shared layers** : the last `num_kv_shared_layers` of
the transformer reuse the K/V projections produced by earlier layers
(see `make_cache` in `mlx_lm/models/gemma4_text.py`):

```python
first_kv_shared = num_hidden_layers - num_kv_shared_layers
# layers[i].self_attn has no k_proj/v_proj for i >= first_kv_shared
```

However, the **safetensors files published on HuggingFace still contain**
the (redundant) `k_proj`, `v_proj`, and `k_norm` weights for those shared
layers. Without filtering, `model.load_weights(..., strict=True)` rejects
them. The non-quantized path silently worked because the safetensors do
not always include those keys, but quantized exports (4-bit, 8-bit) do.

## Fix

Filter the redundant keys inside `Gemma4ForCausalLM.sanitize()`:

```python
def sanitize(self, weights):
    sanitized = {}
    first_kv_shared = self.args.num_hidden_layers - self.args.num_kv_shared_layers
    for k, v in weights.items():
        # ... existing filters ...

        # KV-shared layers reuse K/V from earlier layers — drop their projections
        if any(
            s in k
            for s in (".self_attn.k_proj", ".self_attn.v_proj", ".self_attn.k_norm")
        ):
            try:
                layer_idx = int(k.split("layers.")[1].split(".")[0])
                if layer_idx >= first_kv_shared:
                    continue
            except (IndexError, ValueError):
                pass
        # ...
```

Full patch : [`patches/mlx_lm_gemma4_text_kv_shared.patch`](../patches/mlx_lm_gemma4_text_kv_shared.patch).

## Provenance of the patch on our machines

- **macM1** (`~/mlx-stack/.venv/lib/python3.12/site-packages/mlx_lm/models/gemma4_text.py`)
  - Patched on disk on **2026-05-06 09:48:16** (mtime/ctime).
  - Byte-identical to `ml-explore/mlx-lm@main` after merge commit
    `df1d3f3c9a7aae402dcbb8f41d4c36bcc13a50ae` (2026-05-04 22:26 UTC).
  - Most likely : an earlier session installed `mlx-lm` from git main, or
    manually copied the fixed file from the upstream PR. The byte-for-byte
    match (688 lines vs. pristine 0.31.3 wheel's 675) confirms it is the
    upstream-merged version, not a local invention.
- **Studio M3 Ultra** : currently runs the **pristine** `mlx-lm==0.31.3`
  from PyPI (675 lines) — vulnerable.

## Workaround for any other machine

Until `mlx-lm > 0.31.3` lands on PyPI, do **one** of:

1. **Install mlx-lm from main** :
   ```bash
   uv pip install --force-reinstall \
     "mlx-lm @ git+https://github.com/ml-explore/mlx-lm@main"
   ```

2. **Apply the patch in place** :
   ```bash
   cd ~/electron-bench
   patch -p1 -d "$(python -c 'import mlx_lm, os; print(os.path.dirname(mlx_lm.__file__))')/.." \
     < patches/mlx_lm_gemma4_text_kv_shared.patch
   ```

3. **Copy the patched file from macM1** :
   ```bash
   scp macM1:~/mlx-stack/.venv/lib/python3.12/site-packages/mlx_lm/models/gemma4_text.py \
     "$(python -c 'import mlx_lm, os; print(os.path.dirname(mlx_lm.__file__))')/models/gemma4_text.py"
   ```

## Upstream references

- Issue : https://github.com/ml-explore/mlx-lm/issues/1242 — *"Error when
  using mlx-community/gemma-4-e4b-it-4bit"* (opened 2026-05-03 by `mikeazo`,
  filed exactly the same `Received 126 parameters not in model` traceback).
- PR : https://github.com/ml-explore/mlx-lm/pull/1240 — *"Fix Gemma 4
  sanitize() not stripping KV projections for shared layers"* by `0k1`
  (Arun Raj), reviewed and approved by `angeloskath`, merged 2026-05-04.
- Merge commit : `df1d3f3c9a7aae402dcbb8f41d4c36bcc13a50ae`.

Since the fix is already in upstream `main`, **no new Issue or PR is
required from us**. We only need to wait for a PyPI release > 0.31.3 or
keep using the patched venv / git-installed `mlx-lm`.

## Note on `mlx` vs `mlx-lm`

This bug lives in **`mlx-lm`**, not in the lower-level `mlx` framework.
Our internal fork `L-electron-Rare/mlx` only patches `device_info.cpp`
for the Metal buffer limit and is unrelated. There is currently **no
`electron-rare/mlx-lm` fork** ; creating one would let us pin the fix
locally if PyPI lags significantly.
