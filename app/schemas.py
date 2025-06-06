from pydantic import BaseModel
from datetime import datetime

class UserDataBase(BaseModel):
	username: str
	first_name: str
	last_name: str | None
	telegram_id: int

class UserCreate(UserDataBase):
	pass

class UserResponse(UserDataBase):
	workload: float
	rating: float
	mark_quantity: int
	status: bool

class TaskBase(BaseModel):
	pass

class TaskCreate(BaseModel):
	creator_id: int
	expire_at: datetime
	task_description: str
	status: str
	file_id: str | None

	executors_username: list[str]