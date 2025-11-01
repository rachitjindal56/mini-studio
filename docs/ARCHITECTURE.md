# Mini Studio Architecture

This document outlines the high-level architecture and component responsibilities for the Mini Studio backend.

Overview

Mini Studio is a backend service (FastAPI) that provides dataset management, fine-tuning job orchestration, and model deployment/inference for open-source LLMs. The system is designed to work both locally and in distributed/clustered environments (Ray for training, Kubernetes for serving).

Primary components

- API & Lifespan (main.py)
  - FastAPI app with a lifespan context manager that connects to MongoDB and Redis on startup and closes connections on shutdown.
  - Global middleware: CORS, GZip and structured request/response logging.

- Database (MongoDB)
  - `app/database/mongo.py` provides a singleton `mongodb` Motor client used for storing jobs, datasets metadata, and model routing entries.
  - Collections of interest: `fine_tuning_jobs`, `fine_tuning_datasets`, `model_routing`, `client_config`.

- Cache (Redis)
  - `app/database/redis.py` provides `AsyncRedisClientConfigManager` which caches per-client configuration (`client_config`) with TTL and fallback to MongoDB.

- Object Storage (S3 / DFS)
  - Datasets uploaded via API are saved to a local DFS path (configurable via DFS_BASE_PATH) and optionally uploaded to S3 using `app/clients/boto.py`.
  - `FineTuningService` persists dataset metadata in MongoDB.

- Fine-tuning orchestration
  - `app/services/fine_tuning/service.py` handles dataset saves, dataset metadata persistence, job creation and resource estimation, and enqueues background processing.
  - Background execution tries to submit jobs to Ray via `app/clients/ray_fine_tuning.py`. If Ray is unavailable, it falls back to local simulation.
  - Jobs are persisted in MongoDB and kept updated with status and any Ray job id.

- Ray client
  - `app/clients/ray_fine_tuning.py` wraps Ray initialization and job submission (JobSubmissionClient or a task fallback). It provides cluster resource queries and job status lookups.

- Inference / Deployment (Kubernetes)
  - `app/services/inference/service.py` contains logic to deploy base and fine-tuned models to Kubernetes by creating Deployments, Services, PVCs and KEDA ScaledObjects.
  - Deployed model routing information is stored in MongoDB (`model_routing`) so the API can reverse-proxy inference requests to the correct service URL.
  - Inference proxy uses `httpx` to forward requests to the model service's /predict endpoint.

- Clients & utilities
  - `app/clients/boto.py` — S3 client wrapper.
  - `utility/utils.py` — small helpers (e.g., current UTC time) used by the logging middleware.

- Logging
  - `app/middleware/logger/logging.py` implements JSON file logging with daily files, and middleware that logs incoming requests, outgoing responses, and database operations. Uses contextvars to propagate request_id.

Data flow for a fine-tuning job

1. Client uploads a dataset via /fine_tuning/upload-dataset -> saved to DFS and S3, metadata persisted to `fine_tuning_datasets`.
2. Client calls /fine_tuning/submit-finetune with dataset reference and hyperparameters.
3. Service computes resource estimates, persists a `fine_tuning_jobs` document and enqueues background processing.
4. Background task tries to submit a Ray job to run the training entrypoint (FINETUNING_SCRIPT_PATH). Ray returns a job id recorded in the job doc.
5. After training completes the fine-tuned artifact is available (via DFS/S3). A user may deploy it via /inference/deploy/fine_tuned.
6. The deployed service is recorded in `model_routing` and inference requests are proxied to it.

Resilience and fallbacks

- If MongoDB is unavailable, the fine-tuning service falls back to an in-memory job cache.
- If Ray is unavailable, job processing can be simulated locally or run via a Ray task fallback.
- Redis caching is best-effort: on cache misses the system queries MongoDB and refreshes Redis.

Security and considerations

- Credentials and cluster config are loaded from env files (see `configs/envs.py`). Keep these files secure.
- Kubernetes and Ray interactions use local kubeconfig or in-cluster config depending on runtime.

Where to look in code

- `main.py` — app initialization and middleware
- `app/services/fine_tuning` — fine-tuning API and service logic
- `app/services/inference` — deployment and inference proxy
- `app/database` — mongo and redis helpers
- `app/clients` — S3 and Ray utility wrappers
- `app/middleware/logger` — structured logging and middleware
