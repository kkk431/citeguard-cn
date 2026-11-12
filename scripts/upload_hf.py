"""Create/update the public HuggingFace dataset and adapter repos.

Usage:
  $env:HF_TOKEN = "hf_..."   # or put HF_TOKEN=... in .env.hf
  python scripts/upload_hf.py

Repos (under the token owner):
  dataset: claimsupport-cn-300
  model:   citeguard-support-lora-qwen3-1.7b
"""
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, create_repo, upload_folder

TOKEN = os.environ.get("HF_TOKEN") or ""
if not TOKEN:
    env = Path(".env.hf")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("HF_TOKEN="):
                TOKEN = line.split("=", 1)[1].strip()
if not TOKEN:
    sys.exit("HF_TOKEN missing (env or .env.hf)")

api = HfApi(token=TOKEN)
user = api.whoami()["name"]
dataset_id = f"{user}/claimsupport-cn-300"
model_id = f"{user}/citeguard-support-lora-qwen3-1.7b"


def prep_dataset(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "claimsupport_cn_300.jsonl").write_bytes((src / "claimsupport_cn_300.jsonl").read_bytes())
    (dst / "claimsupport_cn_300.stats.json").write_bytes((src / "claimsupport_cn_300.stats.json").read_bytes())
    if (src / "human_review_40.csv").exists():
        (dst / "human_review_40.csv").write_bytes((src / "human_review_40.csv").read_bytes())
    card = (src / "DATASET_CARD.md").read_text(encoding="utf-8")
    header = "---\nlicense: cc-by-4.0\ntask_categories:\n- text-classification\nlanguage:\n- zh\ntags:\n- citation-verification\n- claim-support\npretty_name: ClaimSupport-CN-300\n---\n\n"
    (dst / "README.md").write_text(header + card, encoding="utf-8")


def prep_model(adapter_src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "adapter_config.json").write_bytes((adapter_src / "adapter_adapter_config.json").read_bytes())
    (dst / "adapter_model.safetensors").write_bytes((adapter_src / "adapter_model.safetensors").read_bytes())
    (dst / "metrics.json").write_bytes((adapter_src / "metrics.json").read_bytes())
    (dst / "eval_predictions.jsonl").write_bytes((adapter_src / "eval_predictions.jsonl").read_bytes())
    card = (adapter_src / "adapter_README.md").read_text(encoding="utf-8")
    header = "---\nbase_model: Qwen/Qwen3-1.7B\nlibrary_name: peft\nlicense: apache-2.0\nlanguage:\n- zh\n---\n\n"
    (dst / "README.md").write_text(header + card, encoding="utf-8")
    scripts = Path("scripts")
    (dst / "training").mkdir(exist_ok=True)
    for name in ("build_support_sft.py", "train_support_lora.py", "eval_support_adapter.py"):
        if (scripts / name).exists():
            (dst / "training" / name).write_bytes((scripts / name).read_bytes())


tmp_ds = Path("out/hf_dataset")
tmp_model = Path("out/hf_model")
prep_dataset(Path("data/claimsupport_cn"), tmp_ds)
prep_model(Path("dist/models/support_lora_qwen3_1.7b"), tmp_model)

for repo_type, repo_id, tmp in (("dataset", dataset_id, tmp_ds), ("model", model_id, tmp_model)):
    create_repo(repo_id, repo_type=repo_type, private=False, exist_ok=True, token=TOKEN)
    upload_folder(
        folder_path=str(tmp),
        repo_id=repo_id,
        repo_type=repo_type,
        token=TOKEN,
        commit_message="CiteGuard-CN v1.0.12: dataset/adapter release",
    )
    print(f"uploaded {repo_type}: https://huggingface.co/{repo_type}s/{repo_id}")

print("DONE")
