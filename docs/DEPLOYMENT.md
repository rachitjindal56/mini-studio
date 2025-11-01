# Deployment & Operations

This document covers deployment, configuration and operational considerations for Mini Studio.

Environment variables

Configured via `.env` files. See `configs/envs.py` for expected keys. Essential variables:

- DATABASE_NAME
- MONGODB_URL
- REDIS_HOST
- REDIS_PORT
- REDIS_USERNAME (optional)
- REDIS_PASSWORD (optional)
- AWS_BUCKET_NAME (optional)
- AWS_REGION
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- PORT
- DFS_BASE_PATH
- FINETUNING_SCRIPT_PATH
- RAY_HEAD_ADDRESS (optional)

Local development

1. Create a `.env` file (or use provided environment mechanism). Ensure MongoDB and Redis are running.
2. Install dependencies (use a virtualenv):
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
3. Run the app:
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Docker

- The provided `Dockerfile` can be used to build a container image for the service.
- Ensure runtime environment variables are injected via your deployment system or Docker run.

Kubernetes

- `InferenceService` expects to run `kubectl`-style operations via the Kubernetes Python client. In-cluster or kubeconfig-based execution is supported.
- Deploy model containers (vllm-server image is referenced in the code). Ensure GPU nodes, device plugin (NVIDIA), and KEDA operator are installed for autoscaling.
- PVCs: fine-tuned deploy creates a PVC per client; ensure default StorageClass and capacity are available.

Ray

- Ray is optional. If available, the app will submit training jobs to Ray via JobSubmissionClient or run a remote Ray task fallback.
- For production distributed training, create a Ray cluster (head + workers) and set `RAY_HEAD_ADDRESS` to connect.

S3 & DFS

- Uploaded datasets are saved to a local DFS path (DFS_BASE_PATH) and optionally uploaded to S3. Provide AWS credentials for S3 upload.

Logging & Monitoring

- App logs: structured JSON files are written to `logs/request_logs_YYYY-MM-DD.json`.
- Kubernetes-deployed model services should expose Prometheus metrics that KEDA can use to autoscale (code expects a `vllm:num_requests_waiting` metric).

Security

- Protect the `.env` files and Kubernetes kubeconfig files.
- Consider adding authentication/authorization to API endpoints (currently not included).

Backups & Persistence

- MongoDB should be backed up (job history and routing info stored there).
- S3 is recommended for long-term storage of datasets and trained artifacts.

Operational tips

- Use separate namespaces per environment in Kubernetes to avoid collisions.
- Monitor Ray cluster resource usage and node GPU availability.
- Tune KEDA thresholds and resource requests/limits based on traffic and model memory footprints.

Troubleshooting

- If deployments fail with ApiException, inspect Kubernetes events and API server logs.
- If Ray jobs do not start, check Ray logs and the head node connectivity.
- If S3 uploads fail, verify AWS credentials and bucket policies.

