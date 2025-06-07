from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from aiogram.utils.text_decorations import HtmlDecoration as htd
import requests
import json

from app.schemas import UserCreate, TaskCreate, UserResponse
from models import DatabaseHelper, User, Task, Team
from app.utils.redis_client import RedisUsers
from config import settings

notifications_tasks_variants = {
	"completed": (
			f"🤝 Задача успешно выполнена!\n\n"
			f"🆔 ID задачи: #ID\n"
			f"📋 Описание: #DESCRIPTION\n"
			f"🔄 Статус: completed ✅\n\n"
			f"🎉 Задача успешно подтверждена заказчиком, ваш рейтинг будет повышен нашей системой автоматически ( будет дана максимальная оценка - 5️⃣), если вдруг заказчик забудет поставить вам оценку или не захочет"
		),
	"canceled": (
			f"⚠️ Задача отменена!\n\n"
			f"🆔 ID задачи: #ID\n"
			f"📋 Описание: #DESCRIPTION\n"
			f"⏳ Срок выполнения: #EXPIRE_AT\n"
			f"🔄 Статус: canceled ❌\n\n"
			f"Задача больше не активна.\n"
			f"☹️ С сожалением сообщаем, что система автоматически понизит ваш рейтинг из-за того, что вы не выполнили задачу в срок!"
		)
}

#? USER REQUESTS
async def set_user_in_db(user_data: UserCreate):
	response = ["is_registred"]
	print("reg", user_data)
	async with DatabaseHelper() as session:
		async with RedisUsers() as redis_client:
			redis_user = await redis_client.get(f"user:{str(user_data.telegram_id)}")
			if redis_user is None:
				print("[+] Redis user is None")
				created_user = await session.scalar(select(User).where(User.telegram_id == user_data.telegram_id))
				if created_user is None:
					print("[+] Created_user is None")
					NewUser = User(
						**user_data.model_dump()
					)
					session.add(NewUser)
					print(f"[+] New user was create: {NewUser.first_name}")
					await session.commit()
					response[0] = "not_registred"
					new_redis_user = NewUser.__dict__
					new_redis_user.pop("_sa_instance_state")
					await redis_client.set(name=f"user:{user_data.telegram_id}", value=json.dumps(new_redis_user))
					response.append(UserResponse(
						first_name=user_data.first_name,
						last_name=user_data.last_name,
						telegram_id=user_data.telegram_id,
						username=user_data.username,
						mark_quantity=0,
						rating=0.0,
						status=True,
						workload=0.0
					))
					print("User create in redis and postgresql")
					return response
				new_redis_user = created_user.__dict__
				new_redis_user.pop("_sa_instance_state")
				await redis_client.set(name=f"user:{user_data.telegram_id}", value=json.dumps(new_redis_user))
				response.append(created_user)
				return response
			redis_user = json.loads(redis_user)
			response.append(UserResponse(
				first_name=redis_user["first_name"],
				last_name=redis_user["last_name"],
				telegram_id=redis_user["telegram_id"],
				username=redis_user["username"],
				mark_quantity=redis_user["mark_quantity"],
				rating=redis_user["rating"],
				status=redis_user["status"],
				workload=redis_user["workload"]
			))
			return response
		
async def get_user_data(user_id: int):
	async with DatabaseHelper() as session:
		async with RedisUsers() as redis_client:
			user_data = await redis_client.get(f"user:{str(user_id)}")
			if user_data is None:
				print("Redis is None")
				user_data = await session.scalar(select(User).where(User.telegram_id == user_id))
				if user_data is None:
					return ["not_registred", None]
				print(f"User data: {user_data.telegram_id}")
				new_redis_user = user_data.__dict__
				new_redis_user.pop("_sa_instance_state")
				await redis_client.set(f"user:{user_data.telegram_id}", json.dumps(new_redis_user))
			else:
				user_data = json.loads(user_data)
				user_data = UserResponse(
					first_name=user_data["first_name"],
					last_name=user_data["last_name"],
					telegram_id=user_data["telegram_id"],
					username=user_data["username"],
					mark_quantity=user_data["mark_quantity"],
					rating=user_data["rating"],
					status=user_data["status"],
					workload=user_data["workload"],					
				)
			status = "not_registred" if user_data is None else "is_registred"
			return [status, user_data]
	
async def get_team_executors(user_id: int):
	async with DatabaseHelper() as session:
		teams = await session.scalars(select(Team).where(Team.creator_id == user_id))
		return teams.all()

async def get_executors_from_team(team_id: int):
	async with DatabaseHelper() as session:
		team = await session.scalar(select(Team).options(selectinload(Team.executors)).where(Team.id == team_id))
		executors = filter(lambda x: x.status == True, team.executors)
		return list(executors)

async def change_status(user_id: int):
	async with DatabaseHelper() as session:
		async with RedisUsers() as redis_client:
			user_data = await session.scalar(select(User).where(User.telegram_id == user_id))
			setattr(user_data, "status", not user_data.status)
			await session.commit()
			new_redis_data = user_data.__dict__
			new_redis_data.pop("_sa_instance_state")
			await redis_client.set(f"user:{user_id}", json.dumps(new_redis_data))
			return new_redis_data["status"]
	
#? TASKS REQUESTS
async def get_processed_tasks(user_id: int):
	async with DatabaseHelper() as session:
		user_data = await session.scalar(select(User).options(selectinload(User.tasks_as_creator)).where(User.telegram_id == user_id))
		tasks = user_data.tasks_as_creator
		return tasks
	
async def get_processed_task(task_id: int):
	async with DatabaseHelper() as session:
		processed_task = await session.scalar(select(Task).options(selectinload(Task.executors)).where(task_id == Task.id))
		return processed_task
	
async def update_executors_in_task(task_id: int, new_executors_usernames: list[str]):
	async with DatabaseHelper() as session:
		processed_task = await session.scalar(select(Task).options(selectinload(Task.executors)).where(task_id == Task.id))
		existing_executors = [i.username for i in processed_task.executors]
		new_executors = await session.scalars(select(User).where(User.username.in_(new_executors_usernames), User.username.not_in(existing_executors)))
		processed_task.executors.extend(list(new_executors))
		await session.commit()
		notification_text = (
			f"🔔 Вы были добавлены в список исполнителей задачи!\n\n"
			f"🆔 ID задачи: {processed_task.id}\n"
			f"📋 Описание: {processed_task.task_description}\n"
			f"⏳ Срок выполнения: {processed_task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"🔄 Статус: {processed_task.status}\n\n"
			f"❗️ Пожалуйста, ознакомьтесь с деталями и начните выполнение вовремя!"
		)
		api_path = f"{settings.BOT_API_URL}{settings.BOT_TOKEN}"
		api_path += "/sendDocument?chat_id={telegram_id}&caption=" + notification_text + f"&document={processed_task.file_id}" if processed_task.file_id else "/sendMessage?chat_id={telegram_id}&text=" + notification_text
		for executor in new_executors.all():
			requests.get(api_path.format(telegram_id=executor.telegram_id))
		return [processed_task, existing_executors]

async def create_task(task_data: TaskCreate):
	async with DatabaseHelper() as session:
		model_dump = task_data.model_dump()
		executors_username = model_dump.pop("executors_username")
		new_task = Task(**model_dump)
		session.add(new_task)
		await session.commit()

		created_task = await session.scalar(
			select(Task).options(selectinload(Task.executors)).where(Task.id == new_task.id)
		)
		executors = await session.scalars(
			select(User).where(User.username.in_(executors_username))
		)
		created_task.executors = list(executors)
		await session.commit()
		notification_text = (
			f"🔔 Новое задание получено!\n\n"
			f"🆔 ID задачи: {created_task.id}\n"
			f"📋 Описание: {created_task.task_description}\n"
			f"⏳ Срок выполнения: {created_task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"🔄 Статус: {created_task.status}\n\n"
			f"❗️ Пожалуйста, ознакомьтесь с деталями и начните выполнение вовремя!"
		)
		api_path = f"{settings.BOT_API_URL}{settings.BOT_TOKEN}"
		api_path += "/sendDocument?chat_id={telegram_id}&caption=" + notification_text + f"&document={created_task.file_id}" if created_task.file_id else "/sendMessage?chat_id={telegram_id}&text=" + notification_text
		for executor in executors:
			requests.get(api_path.format(telegram_id=executor.telegram_id))
		return created_task
	
async def get_assigned_tasks(user_id: int):
	async with DatabaseHelper() as session:
		assigned_tasks = await session.scalars(select(Task).options(selectinload(Task.executors)).where(Task.creator_id == user_id, Task.status == "in_process"))
		return assigned_tasks.all()
	
async def get_user_tasks(user_id: int):
	async with DatabaseHelper() as session:
		user_data = await session.scalar(select(User).options(selectinload(User.tasks)).where(User.telegram_id == user_id))
		# user_data = await session.scalar(select(User).options(selectinload(User.tasks).selectinload(Task.creator)).where(User.telegram_id == user_id))
		creators = []
		# for i in user_data.tasks:
		# 	creator = await session.scalar(select(Task).options(selectinload(Task.creator)).where(Task.id == i.id))
		# 	creators.append(creator.creator.username)
		return user_data.tasks
	
async def get_all_tasks(user_id: int):
	async with DatabaseHelper() as session:
		assigned_tasks = await session.scalars(select(Task).options(selectinload(Task.executors)).where(Task.creator_id == user_id))
		return assigned_tasks.all()
	
async def stop_task(task_id: int, status: str):
	async with DatabaseHelper() as session:
		process_task = await session.scalar(select(Task).options(selectinload(Task.executors)).where(Task.id == task_id))
		setattr(process_task, "status", status)
		notification_text = notifications_tasks_variants[status].replace("#ID", str(process_task.id)).replace("#DESCRIPTION", process_task.task_description)
		if status == "canceled":
			notification_text.replace("#EXPIRE_AT", process_task.expire_at.strftime('%d.%m.%Y %H:%M'))
		for executor in process_task.executors:
			requests.get(f"{settings.BOT_API_URL}{settings.BOT_TOKEN}/sendMessage?chat_id={executor.telegram_id}&text={notification_text}")
		await session.commit()
		return process_task
	
#? TEAM REQUESTS

async def create_team(creator_id: int, team_name: str, executors_username: list[str] | str):
	async with DatabaseHelper() as session:
		new_team = Team(
			name=team_name,
			creator_id=creator_id
		)
		creator = await session.scalar(select(User).where(User.telegram_id == creator_id))
		failed_executors = []
		if executors_username != ".":
			new_executors = await session.scalars(select(User).where(User.username.in_(executors_username), User.username != creator.username))
			new_team.executors = list(new_executors)
			for executor in new_team.executors:
				message_text = (
					f"🎉 Вы были добавлены в команду *{team_name}*! 🎉\n\n"
					f"👑 Заказчик: @{creator.username}\n"
					f"👥 Команда:\n"
				)
				for member in executors_username:
					message_text += f"- @{member}\n"
				message_text += "\nУдачи в работе! 🚀"
				requests.get(f"{settings.BOT_API_URL}{settings.BOT_TOKEN}/sendMessage?chat_id={executor.telegram_id}&text={message_text}&parse_mode=HTML")
			executors_in_db = [i.username for i in new_team.executors]
			failed_executors = [i for i in executors_username if i not in executors_in_db]
			print(failed_executors, [i.username for i in new_team.executors], executors_username)
		session.add(new_team)
		await session.commit()
		return [new_team, failed_executors, creator]

async def get_teams_as_creator(creator_id: int):
	async with DatabaseHelper() as session:
		teams = await session.scalars(select(Team).where(Team.creator_id == creator_id).options(selectinload(Team.executors), selectinload(Team.creator)))
		return teams.all()
	
async def delete_team(team_name: int):
	async with DatabaseHelper() as session:
		team = session.scalar(select(Team).where(Team.name == team_name))
		await session.delete(team)
		await session.commit()
		return team
	
	
async def update_team_executors(team_id: int, new_executors: list[str]):
	async with DatabaseHelper() as session:
		team = await session.scalar(select(Team).options(selectinload(Team.executors), selectinload(Team.creator)).where(Team.id == team_id))
		if team:
			new_executors = await session.scalars(select(User).where(User.username.in_(new_executors)))
			team.executors.extend(list(new_executors))
			await session.commit()
			for executor in new_executors:
				message_text = (
					f"🎉 Вы были добавлены в команду *{team.name}*! 🎉\n\n"
					f"👑 Заказчик: @{team.creator.username}\n"
				)
				message_text += "\nУдачи в работе! 🚀"
				requests.get(f"{settings.BOT_API_URL}{settings.BOT_TOKEN}/sendMessage?chat_id={executor.telegram_id}&text={message_text}&parse_mode=HTML")
			return team
		return None
	
async def get_team(team_name: str):
	async with DatabaseHelper() as session:
		existing_team = await session.scalar(select(Team).where(Team.name == team_name))
		return existing_team