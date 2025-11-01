# Mini Studio API Reference

This document summarizes the main API endpoints exposed by the Mini Studio backend and the expected payloads. All endpoints are prefixed by the FastAPI server host and port (e.g., `http://localhost:8000`).

Root

- GET / — Welcome message
- GET /health — Health check

Fine-tuning API (prefix `/fine_tuning`)

1. GET /fine_tuning/cluster-status
   - Description: Returns Ray cluster resources or a stub if Ray is unavailable.
   - Response: {"ok": true, "status": {...}}

2. GET /fine_tuning/jobs/client/{client_code}
   - Description: List all fine-tuning jobs for the given client
   - Response: {"ok": true, "jobs": [ ... ]}

3. GET /fine_tuning/jobs/{job_id}
   - Description: Get status and metadata for a job
   - Response: {"ok": true, "job": { ... }} or 404 if not found

4. POST /fine_tuning/upload-dataset/{client_code}
   - Description: Upload a training dataset file (multipart/form-data)
   - Request: multipart file field named `file`
   - Response (201): {"ok": true, "dataset_id": "...", "dataset_dfs": "...", "dataset_s3": "...", "size_bytes": 12345}

5. POST /fine_tuning/submit-finetune
   - Description: Submit a fine-tuning job. The service supports payloads compatible with `FineTuningJobRequest` pydantic model.
   - Body (JSON):
     {
       "model": "<model_name_or_id>",
       "n_epochs": 1,
       "batch_size": 64,
       "client_code": "acme",
       "dataset_filename": "<dataset_id_or_path_or_s3_key>",
       "prompt_loss_weight": 0.1,
       "learning_rate_multiplier": 0.1
     }
   - Response (201): {"ok": true, "job": { ... }}

Notes
- `dataset_filename` accepts an uploaded dataset id (string), an S3 key, a DFS path, or a direct upload file object (UploadFile). If it's a string the service tries to resolve it from the `fine_tuning_datasets` collection.

Inference API (prefix `/inference`)

1. POST /inference/deploy/base
   - Deploys an open-source/base model to Kubernetes.
   - Request body (`BaseModelDeployRequest`):
     {
       "client_code": "",
       "model_id": "facebook/opt-125m",
       "gpu_count": 1,
       "min_replicas": 1,
       "max_replicas": 2,
       "prometheus_threshold": 5
     }
   - Response: {"status": "deployed", "deployment": "vllm-base-..."}

2. POST /inference/deploy/fine_tuned
   - Deploys a per-client fine-tuned model (expects weights to be accessible via a PVC mount path).
   - Request body (`FineTunedDeployRequest`):
     {
       "client_code": "acme",
       "base_model": "gpt-neo",
       "fine_tuned_weights_path": "/models/acme/myweights",
       "gpu_count": 1
     }
   - Response: {"status": "deployed", "deployment": "vllm-ft-acme-gpt-neo"}

3. POST /inference/infer/{model_name}
   - Proxy an inference request to the deployed model service. The proxy looks up routing for `model_name` and `X-User-ID` from MongoDB.
   - Headers: `X-User-ID` (optional, used to resolve per-client routing)
   - Body: JSON payload forwarded to the model service `/predict` endpoint.
   - Response: whatever the underlying model service returns (proxied).

Models and Internal Types

- FineTuningJobRequest (pydantic): model, n_epochs, batch_size, client_code, dataset_filename, prompt_loss_weight, learning_rate_multiplier
- BaseModelDeployRequest (pydantic): client_code, model_id, gpu_count, min_replicas, max_replicas, prometheus_threshold
- FineTunedDeployRequest (pydantic): client_code, base_model, fine_tuned_weights_path, gpu_count, min_replicas, max_replicas, prometheus_threshold

Error handling

- Most endpoints return JSON with `{"ok": false, "error": "..."}` on failure and appropriate HTTP status codes.
- Kubernetes API errors are re-raised as ApiException; client should expect 500 responses.

Examples

Upload dataset (curl):

curl -X POST "http://localhost:8000/fine_tuning/upload-dataset/acme" -F "file=@/path/to/dataset.jsonl"

Submit job (curl):

curl -X POST "http://localhost:8000/fine_tuning/submit-finetune" -H "Content-Type: application/json" -d '{"model":"my-model","n_epochs":1,"batch_size":64,"client_code":"acme","dataset_filename":"dataset_id"}'

Deploy base model (curl):

curl -X POST "http://localhost:8000/inference/deploy/base" -H "Content-Type: application/json" -d '{"model_id":"facebook/opt-125m","client_code":"","gpu_count":1}'
