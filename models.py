from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, relationship, declared_attr
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, async_scoped_session
from sqlalchemy import Integer, Column, ForeignKey, String, DateTime, Boolean, BigInteger, UniqueConstraint, func, Float
from typing import List
import asyncio
from datetime import datetime

from config import settings

class Base(DeclarativeBase):
	__abstract__ = True
	
	@declared_attr.directive
	def __tablename__(cls) -> str:
		return f"{cls.__name__.lower()}s"
	
	@declared_attr
	def id(cls):
		if cls.__name__.lower() != "user":
			return Column(Integer, primary_key=True, index=True)

class User(Base):
	telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
	first_name: Mapped[str] = mapped_column(String(35), nullable=False)
	last_name: Mapped[str] = mapped_column(String(35), nullable=True)
	username: Mapped[str] = mapped_column(String(35), nullable=False)
	workload: Mapped[float] = mapped_column(Float, default=0, server_default="0")
	rating: Mapped[float] = mapped_column(Float, default=0, server_default="0")
	mark_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
	status: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

	tasks: Mapped[List["Task"]] = relationship(secondary="task_user_association", back_populates="executors", primaryjoin="User.telegram_id == TaskUserAssociation.user_id")
	teams_as_executor: Mapped[List["Team"]] = relationship(
		secondary="team_executor_association",
		back_populates="executors",
	)
	tasks_as_creator: Mapped[List["Task"]] = relationship(
		"Task",
		back_populates="creator",
		primaryjoin="and_(Task.creator_id == User.telegram_id, Task.status == 'in_process')"
	)
	teams_as_creator: Mapped["Team"] = relationship("Team", back_populates="creator")

class Team(Base):
	name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
	creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)

	creator: Mapped["User"] = relationship(
		"User",
		back_populates="teams_as_creator",
	)
	executors: Mapped[List["User"]] = relationship(
		secondary="team_executor_association",
		back_populates="teams_as_executor"
	)

class TeamExecutorAssociation(Base):
	__tablename__ = "team_executor_association"
	__table_args__ = (
		UniqueConstraint("executor_id", "team_id", name="idx_unique_team_user"),
	)
	executor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
	team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"))

class TaskUserAssociation(Base):
	__tablename__ = "task_user_association"
	__table_args__ = (
		UniqueConstraint("task_id", "user_id", name="idx_unique_task_user"),
	)
	task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"))
	user_id: Mapped[BigInteger] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))

class Task(Base):
	creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
	expire_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
	task_description: Mapped[str] = mapped_column(String, nullable=False)
	status: Mapped[str] = mapped_column(String, default="in_process", server_default="in_process") #? in_process | complete | canceled
	file_id: Mapped[str] = mapped_column(String, nullable=True)

	creator: Mapped["User"] = relationship("User")
	executors: Mapped[List["User"]] = relationship(secondary="task_user_association", back_populates="tasks")

	#! НАДО БЫЛО БЫ ПРИВЯЗЫВАТЬ ОТДЕЛЬНУЮ КОМАНДУ К ТАСКЕ, А НЕ ИЗ РАЗНЫХ КОМАНД ПО ЮЗЕРУ, НО ВПРИНЦИПЕ ЛАДНО

class DatabaseHelper:
	def __init__(self, db_url = settings.DB_URL):
		self.engine = create_async_engine(
			url=db_url,
			echo=settings.DB_ECHO
		)
		self.session_factory = async_sessionmaker(
			autoflush=False,
			bind=self.engine,
			expire_on_commit=False
		)
		self._session: AsyncSession | None = None

	async def __aenter__(self) -> AsyncSession:
		self._session = self.session_factory()
		return self._session
	
	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
		if self._session is not None:
			if exc_type is not None:
				await self._session.rollback()
			await self._session.close()
		self._session = None

db = DatabaseHelper()