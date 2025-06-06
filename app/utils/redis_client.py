from config import settings
from redis import asyncio as aioredis

class RedisClientBase:
	def __init__(self, host: str = settings.redis_settings.REDIS_HOST, port: int = settings.redis_settings.REDIS_PORT, protocol: int = settings.redis_settings.REDIS_PROTOCOL):
		self.port = port
		self.protocol = protocol
		self.host = host
		self._redis_client: aioredis.Redis | None = None
		
	async def __aenter__(self) -> aioredis.Redis:
		self._redis_client = await aioredis.Redis(host=self.host, port=self.port, decode_responses=True)
		return self._redis_client
	
	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
		if self._redis_client is not None:
			if exc_type is not None:
				print(exc_type)
			await self._redis_client.close()
			self._redis_client = None

	@property
	def redis_client(self) -> aioredis.Redis:
		if self._redis_client is not None:
			return self._redis_client
		raise Exception("Please use context manager for Redis")
	
class RedisUsers(RedisClientBase):
	pass