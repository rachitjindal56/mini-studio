# Mini Studio Backend

Mini Studio is a FastAPI backend that provides scalable fine-tuning and model deployment for open-source LLMs. It orchestrates dataset management, fine-tuning job submission (Ray), model artifact storage (DFS + S3), Kubernetes-based model deployment, and a lightweight inference proxy.

## Key features

- Upload and persist fine-tuning datasets to DFS and S3
- Submit fine-tuning jobs that can run on Ray (if available) or local simulation
- Persist job metadata and routing information in MongoDB
- Cache client configuration in Redis for low-latency lookup
- Deploy base and fine-tuned models to Kubernetes (with KEDA scaledobjects for autoscaling)
- Inference reverse-proxy to deployed model services
- Structured file logging and request/response middleware

## Repository layout (important files)

- `main.py` — FastAPI application entrypoint (lifespan hooks connect MongoDB and Redis)
- `app/services/fine_tuning/` — Fine-tuning API (routes, controller, service, model)
- `app/services/inference/` — Inference deploy + proxy (routes, controller, service, model)
- `app/database/mongo.py` — MongoDB singleton wrapper (motor async client)
- `app/database/redis.py` — Redis async client + client config cache
- `app/clients/boto.py` — S3 client wrapper
- `app/clients/ray_fine_tuning.py` — Ray Job API client and helpers
- `app/middleware/logger/logging.py` — Request/response and file JSON logging
- `configs/envs.py` — Environment configuration loader (pydantic + dotenv)
- `fine_tuning_script.py` — (project training entrypoint referenced by Ray)
- `Dockerfile` — Containerization for the service
- `docs/` — Additional documentation (architecture, API, deployment)

## High-level architecture

1. Clients interact with the FastAPI service for dataset uploads, job submission, model deployment, and inference requests.
2. Uploaded datasets are saved to a DFS path and optionally uploaded to S3. Metadata is stored in MongoDB.
3. Submitted fine-tuning jobs are persisted in MongoDB and enqueued for background processing. If Ray is available the job is submitted via Ray Job API; otherwise the service simulates or runs locally.
4. After training, fine-tuned weights can be deployed to Kubernetes using `InferenceService` which creates Deployment, Service, and a KEDA `ScaledObject` for autoscaling.
5. Inference requests are routed through the API which looks up the service URL in MongoDB and proxies the request to the model service.
6. Redis is used as a TTL cache for per-client configuration to avoid frequent MongoDB reads.
7. All requests are logged to daily JSON files and additional structured logs are emitted for DB operations.

## Quickstart (local development)

### Prereqs

- Python 3.10+
- MongoDB (local or remote)
- Redis (local or remote)
- (Optional) Ray cluster for distributed training
- (Optional) Kubernetes cluster for model deploys
- AWS credentials if you want S3 uploads

1. Create an env file for the environment you want to run (see `configs/envs.py` for expected variables). Example `.env` keys:

   ```
   DATABASE_NAME=mini_studio
   MONGODB_URL=mongodb://localhost:27017
   AWS_BUCKET_NAME=your-bucket
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   REDIS_HOST=localhost
   REDIS_PORT=6379
   PORT=8000
   DFS_BASE_PATH=/tmp/mini-studio-dfs
   FINETUNING_SCRIPT_PATH=./fine_tuning_script
   ```

2. Install dependencies

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app

   ```bash
   python main.py
   ```

   Or use uvicorn directly

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Important environment variables

(Defined in `configs/envs.py` Settings)

- DATABASE_NAME, MONGODB_URL — MongoDB configuration
- REDIS_HOST, REDIS_PORT, REDIS_USERNAME, REDIS_PASSWORD — Redis config
- AWS_* — S3 credentials and bucket name
- PORT — application server port
- DFS_BASE_PATH — local DFS base where uploaded datasets are persisted
- FINETUNING_SCRIPT_PATH — path to training entrypoint used by Ray
- RAY_HEAD_ADDRESS — (optional) address for Ray head node

## REST API summary

- GET / — health welcome
- GET /health — health check

Fine-tuning API (/fine_tuning)

- GET /fine_tuning/cluster-status — Return Ray cluster resources (or stub)
- GET /fine_tuning/jobs/client/{client_code} — List jobs for client
- GET /fine_tuning/jobs/{job_id} — Job status
- POST /fine_tuning/submit-finetune — Submit fine-tuning job (body follows FineTuningJobRequest)
- POST /fine_tuning/upload-dataset/{client_code} — Upload dataset file (multipart)

Inference API (/inference)

- POST /inference/deploy/base — Deploy a base model to Kubernetes
- POST /inference/deploy/fine_tuned — Deploy a fine-tuned model to Kubernetes
- POST /inference/infer/{model_name} — Proxy inference request to deployed model

## Where to find detailed docs

- `docs/ARCHITECTURE.md` — architecture and component responsibilities
- `docs/API.md` — API details, request/response examples
- `docs/DEPLOYMENT.md` — deployment notes, Kubernetes, Ray, and Docker tips

## Contributing

Follow existing code patterns. The project uses a singleton pattern for infra clients (MongoDB, Redis, S3, Ray). Logging uses structured JSON files in `logs/`.

## License

(If applicable) Add your license here.
