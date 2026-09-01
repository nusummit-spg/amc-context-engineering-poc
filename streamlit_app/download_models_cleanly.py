# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import os
import time
from huggingface_hub import snapshot_download

def cache_model(repo_id: str, desc: str):
    print(f"[{desc}] Checking/Downloading {repo_id} from HuggingFace...", flush=True)
    for attempt in range(1, 10):
        try:
            path = snapshot_download(repo_id=repo_id, resume_download=True, max_workers=2)
            print(f"[{desc}] Successfully cached at: {path}", flush=True)
            return path
        except Exception as e:
            print(f"[{desc}] Attempt {attempt}/9 failed ({e}). Retrying in {attempt * 3}s...", flush=True)
            time.sleep(attempt * 3)
    print(f"[{desc}] Warning: Could not complete download after 9 attempts.")
    return None

if __name__ == "__main__":
    cache_model("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "SentenceTransformer Embedding")
    cache_model("urchade/gliner_medium-v2.1", "GLiNER NER Model")
