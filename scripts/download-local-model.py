"""Optional model download. Weights are excluded from the project archive."""
from huggingface_hub import snapshot_download
snapshot_download(repo_id="Qwen/Qwen3-1.7B", revision="70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
                  local_dir=".local-models/qwen3-1.7B",
                  allow_patterns=["*.json", "*.safetensors", "*.txt", "LICENSE"])
