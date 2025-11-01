# Mini Studio — System Architecture (Reviewed)

This document is a reviewed, clearer representation of the system architecture derived from `mini_studio_architecture_fixed.drawio`. It describes components, data flows (upload → training → deploy → inference), deployment topology, scaling patterns, failure modes, and recommended improvements.

Summary

Mini Studio is a microservice-style FastAPI backend that orchestrates dataset management, fine-tuning workloads (Ray), model artifact storage (DFS + S3), and model serving on Kubernetes (vLLM-based containers). The backend persists metadata and routing in MongoDB and caches per-client configuration in Redis. Logging is structured (daily JSON files) and middleware captures request/response lifecycle.

Core components

- API (FastAPI)
  - Entrypoint for dataset uploads, job submission, model deployment, and inference proxying.
  - Lifespan hooks connect MongoDB and Redis.
  - Middleware: request/response logging, gzip, CORS.

- Persistent Storage
  - DFS (local filesystem under `DFS_BASE_PATH`) — used for temporary and persisted dataset and model files.
  - S3 (optional) — long-term object store for datasets and model artifacts.
  - MongoDB — stores job metadata (`fine_tuning_jobs`), dataset metadata (`fine_tuning_datasets`), model routing (`model_routing`) and client configs.

- Cache
  - Redis — TTL-based cache for `client_config`; reduces read load on MongoDB.

- Training / Orchestration
  - Ray cluster (optional) — receives job submissions via JobSubmissionClient or a fallback remote task; executes distributed training workloads.
  - `fine_tuning_script.py` — training entrypoint executed by Ray or local fallback.

- Model Serving
  - Kubernetes cluster running model servers (vLLM server image). Each deployed model has:
    - Deployment (Pod with GPU requests/limits)
    - Service (ClusterIP)
    - KEDA ScaledObject (prometheus-triggered autoscaling)
    - Optional PVC for fine-tuned weights
  - Model registry in MongoDB maps model names + client to service URL, used by the inference proxy.

- Observability & Autoscaling
  - Prometheus metrics (expected metric: `vllm:num_requests_waiting`) are used by KEDA to autoscale replicas.
  - Structured file-based logs for API requests and DB operations.

Primary data flows

1. Dataset upload
   - Client POSTs multipart file to `/fine_tuning/upload-dataset/{client_code}`.
   - Service saves file to DFS, optionally uploads to S3, persists metadata to `fine_tuning_datasets` collection.

2. Submit fine-tune job
   - Client POSTs job spec to `/fine_tuning/submit-finetune`.
   - Backend validates payload, estimates resources, creates `fine_tuning_jobs` doc, enqueues background task.
   - Background task attempts to submit a Ray job (JobSubmissionClient) with an entrypoint that points to `fine_tuning_script.py` and dataset path.
   - Ray workers execute training and write checkpoints to DFS/S3; job status updated in MongoDB (job_id / ray_job_id).

3. Deploy model
   - Client calls `/inference/deploy/fine_tuned` or `/inference/deploy/base`.
   - InferenceService creates Deployment, Service, (PVC if needed) and KEDA ScaledObject.
   - Service URL and routing info are persisted in `model_routing` collection.

4. Inference
   - Client POSTs to `/inference/infer/{model_name}`.
   - API looks up routing (client-specific if X-User-ID provided), proxies request to model service `/predict` endpoint, returns response.

Deployment topology and recommendations

- Separate clusters (or namespaces) are recommended:
  - Training workload cluster (Ray) — optimized for GPU training nodes.
  - Inference cluster (Kubernetes) — optimized for GPU/CPU inference with device plugin + KEDA.

- Networking
  - Internal DNS/service discovery used for model routing (ClusterIP `service_name.default.svc.cluster.local`).
  - Protect external endpoints with an API gateway (ingress) and authentication.

Resource & scaling guidance

- Estimate GPU requirements conservatively (service estimates assume 48GB GPU memory per unit).
- Use KEDA + Prometheus metrics for autoscaling; tune `prometheus_threshold` per model type and traffic patterns.
- Use PVCs for per-client model artifacts if model files must be mounted; prefer S3 for portability when possible.

Failure modes & mitigation

- MongoDB down: service falls back to in-memory cache for jobs but loses persistence. Mitigation: Mongo primary/replica sets and backups.
- Redis down: increased MongoDB latency; Redis should be deployed as a durable cluster with persistence if used in production.
- Ray unavailable: background job submission falls back to local simulation — monitor and alert for Ray health.
- Kubernetes API errors (ApiException): bubble up to clients as 500; capture events and kube-apiserver logs for diagnostics.

Security considerations

- Secure `.env` and kubeconfig; use secret management (Kubernetes Secrets, Vault) for credentials.
- Add authentication & authorization to API endpoints (JWT/OAuth or mTLS via ingress).
- Limit RBAC permissions given to the service account that operates Kubernetes objects.

Recommended improvements (short roadmap)

1. Add an API gateway (ingress) with auth and rate-limiting.
2. Implement synchronous/asynchronous job status callbacks (webhooks) and a retry strategy for failed submissions.
3. Replace DFS local paths with a shared POSIX store (NFS) or use S3-backed storage for reproducibility across cluster nodes.
4. Add readiness/liveness probes for long-running background tasks and model deployments.
5. Add integration tests and a Postman/OpenAPI collection for easier onboarding.

Appendix: quick reference to drawio elements

- FastAPI (API entrypoint) → Ray (Job submission) → Ray workers execute training → write checkpoints to S3/DFS → FastAPI triggers Kubernetes deploy → vLLM pods serve requests → registry in MongoDB used by API to proxy inference.

If you want, I can: generate a cleaned drawio export (SVG or updated .drawio) with labeled zones (training vs inference clusters), or produce a Mermaid diagram for README/docs. Which would you prefer next?
