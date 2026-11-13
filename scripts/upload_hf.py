"""Create/update the public HuggingFace dataset and adapter repos.

Usage:
  $env:HF_TOKEN = "hf_..."   # or put HF_TOKEN=... in .env.hf
  python scripts/upload_hf.py [--only all|dataset|1.7b|4b]

Repos (under the token owner):
  dataset: claimsupport-cn-300
  model:   citeguard-support-lora-qwen3-1.7b
  model:   citeguard-support-lora-qwen3-4b
"""
import argparse
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

MODELS = {
    "1.7b": {
        "src": Path("dist/models/support_lora_qwen3_1.7b"),
        "repo": f"{user}/citeguard-support-lora-qwen3-1.7b",
        "base_model": "Qwen/Qwen3-1.7B",
        "pretty_name": "CiteGuard-CN support judge LoRA (Qwen3-1.7B)",
    },
    "4b": {
        "src": Path("dist/models/support_lora_qwen3_4b"),
        "repo": f"{user}/citeguard-support-lora-qwen3-4b",
        "base_model": "Qwen/Qwen3-4B",
        "pretty_name": "CiteGuard-CN support judge LoRA (Qwen3-4B)",
    },
}


def prep_dataset(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "claimsupport_cn_300.jsonl").write_bytes((src / "claimsupport_cn_300.jsonl").read_bytes())
    (dst / "claimsupport_cn_300.stats.json").write_bytes((src / "claimsupport_cn_300.stats.json").read_bytes())
    if (src / "human_review_40.csv").exists():
        (dst / "human_review_40.csv").write_bytes((src / "human_review_40.csv").read_bytes())
    card = (src / "DATASET_CARD.md").read_text(encoding="utf-8")
    header = (
        "---\nlicense: cc-by-4.0\ntask_categories:\n- text-classification\n"
        "language:\n- zh\ntags:\n- citation-verification\n- claim-support\n"
        "pretty_name: ClaimSupport-CN-300\n---\n\n"
    )
    (dst / "README.md").write_text(header + card, encoding="utf-8")


def prep_model(adapter_src: Path, dst: Path, base_model: str, pretty_name: str) -> None:
    if not (adapter_src / "adapter_model.safetensors").exists():
        raise SystemExit(f"adapter weights missing under {adapter_src}")
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "adapter_config.json").write_bytes((adapter_src / "adapter_adapter_config.json").read_bytes())
    (dst / "adapter_model.safetensors").write_bytes((adapter_src / "adapter_model.safetensors").read_bytes())
    for name in ("metrics.json", "eval_predictions.jsonl"):
        if (adapter_src / name).exists():
            (dst / name).write_bytes((adapter_src / name).read_bytes())
    card = (adapter_src / "adapter_README.md").read_text(encoding="utf-8")
    header = (
        f"---\nbase_model: {base_model}\nlibrary_name: peft\nlicense: apache-2.0\n"
        f"language:\n- zh\npretty_name: {pretty_name}\n---\n\n"
    )
    (dst / "README.md").write_text(header + card, encoding="utf-8")
    scripts = Path("scripts")
    (dst / "training").mkdir(exist_ok=True)
    for name in ("build_support_sft.py", "train_support_lora.py", "eval_support_adapter.py"):
        if (scripts / name).exists():
            (dst / "training" / name).write_bytes((scripts / name).read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["all", "dataset", "1.7b", "4b"], default="all")
    args = parser.parse_args()

    if args.only in ("all", "dataset"):
        tmp = Path("out/hf_dataset")
        prep_dataset(Path("data/claimsupport_cn"), tmp)
        create_repo(dataset_id, repo_type="dataset", private=False, exist_ok=True, token=TOKEN)
        upload_folder(
            folder_path=str(tmp), repo_id=dataset_id, repo_type="dataset", token=TOKEN,
            commit_message="CiteGuard-CN: ClaimSupport-CN-300 dataset release",
        )
        print(f"uploaded dataset: https://huggingface.co/datasets/{dataset_id}")

    for key, spec in MODELS.items():
        if args.only not in ("all", key):
            continue
        tmp = Path(f"out/hf_model_{key}")
        prep_model(spec["src"], tmp, spec["base_model"], spec["pretty_name"])
        create_repo(spec["repo"], repo_type="model", private=False, exist_ok=True, token=TOKEN)
        upload_folder(
            folder_path=str(tmp), repo_id=spec["repo"], repo_type="model", token=TOKEN,
            commit_message=f"CiteGuard-CN: support judge LoRA for {spec['base_model']}",
        )
        print(f"uploaded model: https://huggingface.co/{spec['repo']}")

    print("DONE")


if __name__ == "__main__":
    main()
