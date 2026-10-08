from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import snapshot_download

model_id = os.environ.get(
    "JUDICORE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
target = Path(os.environ.get("JUDICORE_EMBEDDING_MODEL_DIR", "./embedding-model"))
target.mkdir(parents=True, exist_ok=True)
snapshot_download(repo_id=model_id, local_dir=target, local_dir_use_symlinks=False)
print(f"Downloaded {model_id} to {target.resolve()}")
