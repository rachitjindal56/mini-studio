import json
import asyncio
import traceback
import redis.asyncio as redis
from typing import Optional, Any
from app.database.mongo import mongodb
from configs.envs import env_variables
from app.database.utils import make_api_call
from motor.motor_asyncio import AsyncIOMotorCollection


class AsyncRedisClientConfigManager:
    _client_config_collection_name = "client_config"
    _instance = None

    def __new__(cls) -> 'AsyncRedisClientConfigManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, redis_client_config_ttl: int = 60):
        self._redis = redis.Redis(
            host=env_variables.REDIS_HOST,
            port=env_variables.REDIS_PORT,
            username=env_variables.REDIS_USERNAME,
            password=env_variables.REDIS_PASSWORD,
            decode_responses=True
        )
        self._client_config_ttl = redis_client_config_ttl
        self._client_config_collection: AsyncIOMotorCollection = mongodb.get_database()[self._client_config_collection_name]

    @staticmethod
    async def get_nested(data: dict, attr_key: str):
        keys = attr_key.split(".")
        for key in keys:
            if not isinstance(data, dict):
                return None
            data = data.get(key)
        return data

    async def check_connection(self) -> bool:
        try:
            await self._redis.ping()
            print("Redis successfully connected")
            return True
        except Exception as e:
            print(f"Redis connection error: {traceback.format_exc()}")
            return False

    async def close_connection(self) -> bool:
        if self._redis:
            await self._redis.close()
            print("Redis connection closed")
            return True
        return False

    async def _load_client_config_from_mongo(self, client_code: str) -> dict | None:
        try:
            return await self._client_config_collection.find_one({"client_code": client_code}, {"_id": 0, 'updated_at': 0})
        except Exception as e:
            return None

    async def get_client_config(self, client_code: str, attrs: Optional[str] = None) -> Any:
        try:
            if attrs:
                cached = await self._redis.get(client_code)
                if cached:
                    return await AsyncRedisClientConfigManager.get_nested(json.loads(cached), attrs)
            else:
                cached = await self._redis.get(client_code)
                if cached:
                    return await AsyncRedisClientConfigManager.get_nested(json.loads(cached), attrs)
        except:
            await self._redis.delete(client_code)

        config_data = await self._load_client_config_from_mongo(client_code)
        if config_data:
            await self._redis.set(client_code,json.dumps(config_data))
            await self._redis.expire(client_code, self._client_config_ttl)

            if attrs:
                return await AsyncRedisClientConfigManager.get_nested(config_data, attrs)
            return config_data
        return await self.get_client_config('default', attrs)


client_config = AsyncRedisClientConfigManager()
