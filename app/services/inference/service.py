import time
import httpx
import logging
from app.database.mongo import mongodb
from fastapi.responses import JSONResponse

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from app.services.inference.model import BaseModelDeployRequest, FineTunedDeployRequest

logger = logging.getLogger(__name__)

# K8s setup (local kubeconfig, fallback to in-cluster)
# Right now using Kubernetes Python client directly for simplicity but would be using Ansible playbooks for production
try:
    config.load_kube_config(config_file="remote-cluster-b-kubeconfig.yaml")
except Exception:
    config.load_incluster_config()

apps_api = client.AppsV1Api()
core_api = client.CoreV1Api()
custom_api = client.CustomObjectsApi()

def create_scaled_object_yaml(deployment_name: str, req):
    return {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": {"name": f"{deployment_name}-scaledobject", "namespace": "default"},
        "spec": {
            "scaleTargetRef": {"name": deployment_name},
            "minReplicaCount": req.min_replicas,
            "maxReplicaCount": req.max_replicas,
            "pollingInterval": 15,
            "cooldownPeriod": 30,
            "triggers": [
                {
                    "type": "prometheus",
                    "metadata": {
                        "serverAddress": "http://prometheus-operated.monitoring.svc:9090",
                        "metricName": "vllm:num_requests_waiting",
                        "query": "vllm:num_requests_waiting",
                        "threshold": str(req.prometheus_threshold),
                    },
                }
            ],
        },
    }


class InferenceService:
    """
    Encapsulates all Kubernetes deploy + inference proxy logic.
    Routes/controllers call into this class.
    """

    def __init__(self):
        self.apps_api = apps_api
        self.core_api = core_api
        self.custom_api = custom_api

    def _create_base_deployment_objects(self, deployment_name, req, container_args, container_env, volume_mounts=None, volumes=None):
        service_name = f"{deployment_name}-svc"
        deployment_body = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": deployment_name, "namespace": "default"},
            "spec": {
                "replicas": req.min_replicas,
                "selector": {"matchLabels": {"app": deployment_name}},
                "template": {
                    "metadata": {"labels": {"app": deployment_name}},
                    "spec": {
                        "containers": [
                            {
                                "name": "vllm",
                                "image": "vllm-server:latest",
                                "args": container_args,
                                "env": container_env,
                                "resources": {
                                    "limits": {"nvidia.com/gpu": str(req.gpu_count)},
                                    "requests": {"nvidia.com/gpu": str(req.gpu_count)},
                                },
                                "ports": [{"containerPort": 8000}],
                                "volumeMounts": volume_mounts or [],
                            }
                        ],
                        "volumes": volumes or [],
                    },
                },
            },
        }

        service_body = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": service_name, "namespace": "default"},
            "spec": {
                "selector": {"app": deployment_name},
                "ports": [{"port": 8000, "targetPort": 8000}],
                "type": "ClusterIP",
            },
        }

        scaled_object = create_scaled_object_yaml(deployment_name, req)
        return deployment_body, service_body, scaled_object, service_name

    async def _save_routing(self, deployment_name: str, service_name: str, model_name: str, client_code: str, is_base: bool):
        try:
            db = mongodb.get_database()
            coll = db.get_collection("model_routing")
            doc = {
                "deployment_name": deployment_name,
                "service_name": service_name,
                "service_url": f"http://{service_name}.default.svc.cluster.local:8000",
                "model_name": model_name,
                "client_code": client_code,
                "is_base": bool(is_base),
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            }
            await coll.update_one({"deployment_name": deployment_name}, {"$set": doc}, upsert=True)
        except Exception:
            logger.exception("Failed to persist model routing to MongoDB; continuing without DB record")

    async def _find_routing(self, model_name: str, client_code: str):
        try:
            db = mongodb.get_database()
            coll = db.get_collection("model_routing")
            if client_code:
                doc = await coll.find_one({"model_name": model_name, "client_code": client_code})
                if doc:
                    return doc.get("service_url")
            doc = await coll.find_one({"model_name": model_name, "is_base": True})
            if doc:
                return doc.get("service_url")
        except Exception:
            logger.exception("Failed to query model_routing collection")
        return None

    async def deploy_base_model(self, req: BaseModelDeployRequest):
        """
        Deploy an open-source / base model. Returns dict with status or raises ApiException.
        """
        deployment_name = f"vllm-base-{req.model_id.split('/')[-1]}"
        service_name = f"{deployment_name}-svc"
        model_name = req.model_id.split("/")[-1]
        container_args = ["--model", req.model_id]
        container_env = [{"name": "HF_HOME", "value": "/models/hf-cache"}]
        volume_mounts = [{"name": "hf-cache", "mountPath": "/models/hf-cache"}]
        volumes = [{"name": "hf-cache", "persistentVolumeClaim": {"claimName": "hf-cache-pvc"}}]

        deployment_body, service_body, scaled_object, _ = self._create_base_deployment_objects(
            deployment_name, req, container_args, container_env, volume_mounts, volumes
        )

        # apply resources
        try:
            self.apps_api.create_namespaced_deployment("default", deployment_body)
            self.core_api.create_namespaced_service("default", service_body)
            self.custom_api.create_namespaced_custom_object(
                group="keda.sh", version="v1alpha1", namespace="default",
                plural="scaledobjects", body=scaled_object
            )
            await self._save_routing(deployment_name, service_name, model_name, "", is_base=True)
            return {"status": "deployed", "deployment": deployment_name}
        except ApiException:
            logger.exception("Kubernetes API error during base deploy")
            raise

    async def deploy_fine_tuned_model(self, req: FineTunedDeployRequest):
        """
        Deploy per-user fine-tuned model. Returns dict with status or raises ApiException.
        """
        deployment_name = f"vllm-ft-{req.client_code}-{req.base_model}"
        service_name = f"{deployment_name}-svc"
        model_name = req.base_model
        pvc_name = f"pvc-{req.client_code}"

        # create pvc if not exist
        pvc_body = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": pvc_name, "namespace": "default"},
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "10Gi"}}
            },
        }
        try:
            self.core_api.create_namespaced_persistent_volume_claim("default", pvc_body)
        except ApiException as e:
            if getattr(e, "status", None) != 409:
                logger.exception("PVC creation failed")
                raise

        container_args = ["--model", req.fine_tuned_weights_path]
        volume_mounts = [
            {"name": f"user-models-{req.client_code}", "mountPath": req.fine_tuned_weights_path}
        ]
        volumes = [
            {"name": f"user-models-{req.client_code}", "persistentVolumeClaim": {"claimName": pvc_name}}
        ]

        deployment_body, service_body, scaled_object, _ = self._create_base_deployment_objects(
            deployment_name, req, container_args, [], volume_mounts, volumes
        )

        try:
            self.apps_api.create_namespaced_deployment("default", deployment_body)
            self.core_api.create_namespaced_service("default", service_body)
            self.custom_api.create_namespaced_custom_object(
                group="keda.sh", version="v1alpha1", namespace="default",
                plural="scaledobjects", body=scaled_object
            )
            await self._save_routing(deployment_name, service_name, model_name, req.client_code, is_base=False)
            return {"status": "deployed", "deployment": deployment_name}
        except ApiException:
            logger.exception("Kubernetes API error during fine-tuned deploy")
            raise

    async def infer_proxy(self, model_name: str, payload: dict, client_code: str):
        """
        Reverse proxy inference request to deployed model.
        """
        target = await self._find_routing(model_name, client_code)
        if not target:
            return JSONResponse(status_code=404, content={"detail": "Model not deployed"})

        async with httpx.AsyncClient() as client:
            resp = await client.post(target + "/predict", json=payload, timeout=60.0)
            try:
                return JSONResponse(status_code=resp.status_code, content=resp.json())
            except Exception:
                return JSONResponse(status_code=resp.status_code, content={"result": resp.text})