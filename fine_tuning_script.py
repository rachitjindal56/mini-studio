import argparse
import os
from pathlib import Path
import requests

# Unsloth fine-tuning
from unsloth.trainer import Trainer
from unsloth.data import Dataset

parser = argparse.ArgumentParser()
parser.add_argument("--model", type=str, required=True, help="Base model name or path")
parser.add_argument("--dataset_path", type=str, required=True, help="Path in DFS to JSONL dataset")
parser.add_argument("--num_gpus", type=int, default=1, help="Number of GPUs to use")
parser.add_argument("--learning_rate", type=float, default=2e-5)
parser.add_argument("--epochs", type=int, default=3)
parser.add_argument("--batch_size", type=int, default=8)
parser.add_argument("--dfs_model_path", type=str, default="/mnt/dfs/models")
parser.add_argument("--backend_api", type=str, default=os.environ.get("BACKEND_API", "http://fastapi-backend:8000"))
parser.add_argument("--job_id", type=str, required=True, help="Ray job ID for tracking")
args = parser.parse_args()

MODEL_NAME = args.model
DATASET_PATH = args.dataset_path
NUM_GPUS = args.num_gpus
LEARNING_RATE = args.learning_rate
EPOCHS = args.epochs
BATCH_SIZE = args.batch_size
DFS_MODEL_PATH = args.dfs_model_path
BACKEND_API = args.backend_api
JOB_ID = args.job_id


def fine_tune_unsloth_model(base_model_path, dataset_path, output_dir):
    print(f"[Job {JOB_ID}] Starting fine-tuning using Unsloth for {base_model_path}")

    # Load dataset
    dataset = Dataset.from_jsonl(dataset_path)

    # Trainer config
    trainer = Trainer(
        model_name_or_path=base_model_path,
        output_dir=output_dir,
        learning_rate=LEARNING_RATE,
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=max(1, NUM_GPUS),
        fp16=True if NUM_GPUS > 0 else False,
        save_strategy="epoch",
        logging_strategy="steps",
        logging_steps=50,
        save_total_limit=3
    )
    trainer.train(dataset)
    print(f"[Job {JOB_ID}] Fine-tuned model saved at {output_dir}")
    return output_dir

# Save fine-tuned model to DFS
model_output_dir = os.path.join(DFS_MODEL_PATH, MODEL_NAME)
os.makedirs(model_output_dir, exist_ok=True)
fine_tune_unsloth_model(MODEL_NAME, DATASET_PATH, model_output_dir)

# Call backend API to deploy model
def deploy_model_backend(model_name, gpu_count):
    url = f"{BACKEND_API}/deploy-model"
    payload = {
        "model_name": model_name,
        "model_path": model_output_dir,
        "port": 8000,
        "replicas": 2,
        "gpu_count": gpu_count
    }
    print(f"[Job {JOB_ID}] Calling backend API to deploy model {model_name}")
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"[Job {JOB_ID}] Failed to deploy model: {resp.text}")
    print(f"[Job {JOB_ID}] Backend deployment response: {resp.json()}")
    return resp.json()

deploy_model_backend(MODEL_NAME, NUM_GPUS)
print(f"[Job {JOB_ID}] Fine-tuning and deployment completed for model {MODEL_NAME}")