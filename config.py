from pydantic.v1 import BaseSettings, BaseModel

class RedisSettings(BaseModel):
	REDIS_HOST: str = "redis"
	REDIS_PORT: int = 6379
	REDIS_PROTOCOL: int = 3
	REDIS_URL: str = "redis://redis:6379/0"
	CACHE_EXPIRATION_MIN: int = 5

class BotSettings(BaseSettings):
	BOT_TOKEN: str = "" #! YOUR BOT TOKEN
	
	DB_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/tasktrackerbot"
	DB_ECHO: bool = True
	LOGGING_DATEFMT: str = "%Y-%m-%d %H:%M:%S"
	redis_settings: RedisSettings = RedisSettings()
	BOT_API_URL: str = "https://api.telegram.org/bot"
	
settings = BotSettings()