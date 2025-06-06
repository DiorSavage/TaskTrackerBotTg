from aiogram import F, Router, Bot
from aiogram import types
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.text_decorations import html_decoration as htd

from app.requests import set_user_in_db, create_task, get_assigned_tasks, get_all_tasks, get_user_data, change_status, create_team, get_teams_as_creator, get_processed_tasks, stop_task, get_team_executors, get_executors_from_team, get_user_tasks, update_team_executors, get_processed_task, update_executors_in_task
from app.schemas import UserCreate, TaskCreate
from app.keyboards import main_keyboard, confirm_task_keyboard, team_choose_keyboard, executor_choose_keyboard, processed_tasks_keyboard
from app.utils.celery_worker import confirm_task, notificate_user

from app.utils.redis_client import RedisUsers

from datetime import datetime

router = Router()

status_emoji = {
	"in_process": "🧑‍💻",
	"completed": "✅",
	"canceled": "❌"
}

class NewTask(StatesGroup):
	task_description = State()
	expire_at = State()
	team = State()
	executors_username = State()
	task_file = State()

class NewTeam(StatesGroup):
	team_name = State()
	executors_username = State()

class AddTeam(StatesGroup):
	team_id = State()
	new_executors = State() #? list[str]

class ExecutorsTask(StatesGroup):
	task_id = State()
	team_id = State()
	executors = State()

@router.message(CommandStart())
async def start_command(message: Message):
	try:
		new_user_data = UserCreate(
			first_name=message.from_user.first_name,
			last_name=message.from_user.last_name,
			username=message.from_user.username,
			telegram_id=message.from_user.id
		)
		[status, user_data] = await get_user_data(user_id=new_user_data.telegram_id)
		if user_data is None:
			[status, user_data] = await set_user_in_db(user_data=new_user_data)
		if status == "not_registred":
			message_text = (
				f"🎉 Добро пожаловать, {user_data.first_name}! 🎉\n\n"
				f"Вы успешно зарегистрированы как @{user_data.username}. ✅\n"
				f"Теперь вы можете взаимодействовать с ботом. 🚀\n"
				f"Выберите действие из меню ниже: 📋"
			)
			await message.answer_photo(
				photo=FSInputFile("./app/images/welcome_image.gif"),
				caption=message_text,
				reply_markup=await main_keyboard(user_data=user_data)
			)
		else:
			message_text = (
				f"👋 Привет, {user_data.first_name}! 👋\n\n"
				f"Выберите действие из меню ниже: 📋"
			)
			await message.answer_photo(
				photo=FSInputFile("./app/images/welcome_image.gif"),
				caption=message_text,
				reply_markup=await main_keyboard(user_data=user_data)
			)
	except Exception as exc:
		print(exc)
		await message.answer("Error with creating a user")

@router.callback_query(F.data == "all_executors")
async def get_all_executors_handler(callback: CallbackQuery):
	teams = await get_teams_as_creator(creator_id=callback.from_user.id)

	if not teams:
		await callback.message.answer("⚠️ Вы еще не создали ни одной команды.")
		return

	message_text = "📋 Список ваших команд:\n\n"
	for team in teams:
		message_text += (
			f"📋 Команда: *{team.name}*\n"
			f"👑 Заказчик: {htd.link(f'@{team.creator.username}', f'tg://user?id={team.creator.telegram_id}')}\n"
			f"👥 Исполнители:\n"
		)
		if team.executors:
			for executor in team.executors:
				message_text += (
					f"- {htd.link(f'@{executor.username}', f'tg://user?id={executor.telegram_id}')} - статус: {"😎 Активен" if executor.status else "😴 Не активен"}\n"
				)
		else:
			message_text += "Исполнители пока не назначены.\n"
		message_text += "\n" + "-" * 30 + "\n"

	await callback.message.answer(text=message_text, parse_mode="HTML")

@router.callback_query(F.data == "set_task")
async def set_task_handler(callback: CallbackQuery, state: FSMContext):
	await callback.message.answer("Введите описание задачи:")
	await state.set_state(NewTask.task_description)

@router.message(NewTask.task_description)
async def process_task_description(message: types.Message, state: FSMContext):
	task_description = message.text.strip()
	if not task_description:
		await message.answer("Описание задачи не может быть пустым. Пожалуйста, введите описание снова.")
		return
	await state.update_data(task_description=task_description)
	await message.answer("Введите дату и время завершения задачи (формат: DD.MM.YYYY HH:MM):")
	await state.set_state(NewTask.expire_at)

@router.message(NewTask.expire_at)
async def process_expire_at(message: types.Message, state: FSMContext):
	expire_at_str = message.text.strip()
	try:
		expire_at = datetime.strptime(expire_at_str, "%d.%m.%Y %H:%M")
	except ValueError:
		await message.answer("Неверный формат даты и времени. Пожалуйста, введите в формате DD.MM.YYYY HH:MM.")
		return
	my_teams = await get_team_executors(message.from_user.id)
	await state.update_data(expire_at=expire_at)
	await message.answer(text="Выберите одну из ваших команд: ", reply_markup=await team_choose_keyboard(my_teams))
	await state.set_state(NewTask.team)

@router.callback_query(NewTask.team, F.data.startswith("team_ex"))
async def process_team(callback: CallbackQuery, state: FSMContext):
	team_id = int(callback.data.split(":")[1])
	executors = await get_executors_from_team(team_id=team_id)
	if not executors:
		await callback.message("🤔 Исполнителей нет либо они не готовы сейчас принимать задания")
		await state.clear()
		return
	message_text = (
		"👥 <b>Список доступных исполнителей:</b>\n\n"
	)
	for executor in executors:
		message_text += (
			f"👤 {executor.username} "
			f"(ID: {executor.telegram_id})\n"
			f"	⚡️ Рабочая нагрузка: {executor.workload}\n"
    	f"	⭐️ Рейтинг: {executor.rating}\n\n"
		)

	await callback.message.answer(
		text=message_text,
		parse_mode="HTML",
		reply_markup=await executor_choose_keyboard(executors=executors, team_id=team_id, is_init=True)
	)
	await state.set_state(NewTask.executors_username)

@router.callback_query(NewTask.executors_username, F.data.startswith("executor"))
async def process_executors_username(callback: CallbackQuery, state: FSMContext):
	team_id = int(callback.data.split(":")[2])
	executors = await get_executors_from_team(team_id=team_id)
	if not executors:
		await callback.message("🤔 Исполнителей нет либо они не готовы сейчас принимать задания")
		await state.clear()
		return
	data = await state.get_data()

	selected_executors = data.get("executors_username") if data.get("executors_username") else []
	selected_executors.append(callback.data.split(":")[1])
	filtered_executors = [i for i in executors if i.username not in selected_executors] if selected_executors else executors
	message_text = "👥 <b>Список доступных исполнителей:</b>\n\n"
	await state.update_data(executors_username=selected_executors)
	for executor in filtered_executors:
		message_text += (
			f"👤 {executor.username} "
			f"(ID: {executor.telegram_id})\n"
			f"	⚡️ Рабочая нагрузка: {executor.workload}\n"
			f"	⭐️ Рейтинг: {executor.rating}\n\n"
		)

	await state.set_state(NewTask.executors_username)
	await callback.message.answer(
		text=message_text,
		parse_mode="HTML",
		reply_markup=await executor_choose_keyboard(executors=filtered_executors, team_id=team_id)
	)

@router.callback_query(NewTask.executors_username, F.data == "save_executors")
async def process_save_executors(callback: CallbackQuery, state: FSMContext):
	data = await state.get_data()
	if not data.get("executors_username"):
		await callback.message.answer("🤬 Вы не выбрали исполнителей!!!\n\n👤 Выберите исполнителя в меню сверху")
		return
	print("Save executors")
	await callback.message.answer("📎 Хотите прикрепить файл к задаче? Если да, отправьте файл.\n❌ Если нет, нажмите /skip_file.")
	await state.set_state(NewTask.task_file)

@router.message(NewTask.task_file, F.document)
async def process_task_file(message: Message, state: FSMContext):
	file_id = message.document.file_id
	print(f"[-1231244123-]{file_id}")
	await state.update_data(task_file=file_id)
	await create_and_save_task(message, state)
	#! ПОДУМАТЬ С СОХРАНЕНИЕМ ФАЙЛОВ

@router.message(NewTask.task_file, F.text == "/skip_file")
async def skip_file_upload(message: Message, state: FSMContext):
	await state.update_data(task_file=None)
	data = await state.get_data()
	print(f"[+] Data: {data}")
	await create_and_save_task(message, state)

async def create_and_save_task(message: types.Message, state: FSMContext):
	async with RedisUsers() as redis_client:
		data = await state.get_data()
		task_data = TaskCreate(
			task_description=data.get("task_description"),
			expire_at=data.get("expire_at"),
			executors_username=data.get("executors_username"),
			creator_id=message.from_user.id,
			status="in_process",
			file_id=data.get("task_file")
		)
		print(f"[+_=] {data.get("task_file")}")
		try:
			created_task = await create_task(task_data)
			task_dict = {
				"id": created_task.id,
				"task_description": created_task.task_description,
				"expire_at": created_task.expire_at.isoformat(),
				"executors_username": ', '.join([executor.username for executor in created_task.executors]),
				"executors_id": [executor.telegram_id for executor in created_task.executors],
				"creator_id": created_task.creator_id,
				"status": created_task.status,
				"file_id": created_task.file_id
			}
			confirm_data = confirm_task.apply_async((task_dict, ), countdown=((created_task.expire_at - datetime.now()).total_seconds()))
			notificate_data = notificate_user.apply_async((task_dict, ), countdown=((created_task.expire_at - datetime.now()).total_seconds() - 300))
			await redis_client.set(f"confirm_task_id:{str(created_task.id)}", confirm_data.id)
			await redis_client.set(f"notificate_task_id:{created_task.id}", notificate_data.id)

			notification_text = (f"✅ Задача успешно создана!\n"
													f"📋 Описание: {created_task.task_description}\n"
													f"⌛ Дата завершения: {created_task.expire_at}\n"
													f"👥 Исполнители: {', '.join([executor.username for executor in created_task.executors])}")
			await message.answer(text=notification_text)
			if created_task.file_id:
				notification_text += f"\n📎 Также был прикреплен файл"
				await message.answer_document(document=created_task.file_id)
			await state.clear()
		except Exception as e:
			await message.answer(f"❌ Произошла ошибка при создании задачи: {str(e)}")
			await state.clear()

async def confirm_task_process(task_id: str):
	async with RedisUsers() as redis_client:
		confirm_task_id = await redis_client.get(f"confirm_task_id:{task_id}")
		notificate_task_id = await redis_client.get(f"notificate_task_id:{task_id}")
		if confirm_task_id and notificate_task_id:
			confirm_task_result = confirm_task.AsyncResult(confirm_task_id)
			notificate_task_result = notificate_user.AsyncResult(notificate_task_id)
			if confirm_task_result and notificate_task_result:
				await redis_client.delete(f"confirm_task_id:{task_id}", f"notificate_task_id:{task_id}")
				confirm_task_result.abort()
				notificate_task_result.abort()
				confirmed_task = await stop_task(task_id=int(task_id), status="completed")
				#! REVOKE - задачи именно остановятся, а у меня блять они еще потом обработаются, но мне в падлу
				# if request.POST.get('stop'):
				# print('stop')
				# celery_app.control.revoke(process_id, terminate=True)
				#! REVOKE
				print("[-] Abort tasks")
				return confirmed_task
		return True

@router.callback_query(F.data == "change_team")
async def change_team_handler(callback: CallbackQuery, state: FSMContext):
	teams = await get_team_executors(user_id=callback.from_user.id)
	if not teams:
		await callback.message.answer("🤔 Вы не создали ни одной команды")
		return
	await callback.message.answer(text=f"👥 Выберите команду", reply_markup=await team_choose_keyboard(teams))
	await state.set_state(AddTeam.team_id)

@router.callback_query(AddTeam.team_id, F.data.startswith("team_ex"))
async def choose_team_handler(callback: CallbackQuery, state: FSMContext):
	team_id = int(callback.data.split(":")[1])
	await state.update_data(team_id=team_id)
	executors = await get_executors_from_team(team_id=team_id)
	if not executors:
		await callback.message("🤔 Исполнителей нет либо они не готовы сейчас принимать задания")
		await state.clear()
		return
	if len(executors) < 2:
		await callback.message.answer(text="⚠️ Вы не можете удалить исполнителей, так как остался один")
	await callback.message.answer(text="📝 Введите username пользователей через запятую без пробелов:")
	await state.set_state(AddTeam.new_executors)

@router.message(AddTeam.new_executors)
async def save_team_changes(message: Message, state: FSMContext):
	new_executors = message.text.split(",")
	data = await state.get_data()
	team_id = data.get("team_id")
	updated_team = await update_team_executors(team_id=team_id, new_executors=new_executors)
	if not updated_team:
		await message.answer("⚠️ К сожалению не удалось добавить новых исполнителей ( команды не существует )")
		return
	await message.answer("✅ Новые исполнители были добавлены")

@router.callback_query(F.data == "confirm_task")
async def confirm_task_handler(callback: CallbackQuery):
	tasks_as_creator = await get_processed_tasks(user_id=callback.from_user.id)
	if not tasks_as_creator:
		await callback.message.answer("⚠️ У вас нет активных задач для закрытия.")
		return

	message_text = "📋 Список ваших активных задач:\n\n"

	for task in tasks_as_creator:
		message_text += (
			f"📝 Задача #{task.id}\n"
			f"📅 Создана: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏰ Срок выполнения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"💬 Описание: {task.task_description}\n\n"
		)
	task_ids = [str(i.id) for i in tasks_as_creator]

	await callback.message.answer(
		text=message_text,
		reply_markup=await confirm_task_keyboard(task_ids=task_ids)
	)

@router.callback_query(F.data.startswith("close_task"))
async def confirm_task_by_id(callback: CallbackQuery):
	task_id = str(callback.data.split(":")[1])
	await confirm_task_process(task_id=task_id)
	await callback.message.answer("Successful confirm task")
	
@router.callback_query(F.data == "my_tasks")
async def get_user_tasks_handler(callback: CallbackQuery):
	tasks = await get_user_tasks(user_id=int(callback.from_user.id))
	if not tasks:
		await callback.message.answer("⚠️ У вас нет активных задач.")
		return
	print(tasks[0].creator_id)
	message_text = "📋 <b>Список ваших задач:</b>\n\n"
	for task in tasks:
		urgency_status = "🚨 СРОЧНО, осталось меньше дня для выполнения" if task.expire_at.date() == datetime.now().date() else "⏳ В процессе"

		message_text += (
			f"<b>Задача #{task.id}</b>\n"
			f"📅 Создана: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏰ Срок завершения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"📝 Описание: {task.task_description}\n"
			# f"👑 Создатель: @{creators[i]}\n"
		)

		if task.expire_at.date() == datetime.now().date():
			message_text += f"❗️ {urgency_status}\n"

		message_text += "\n" + "-" * 30 + "\n"

	await callback.message.answer(
			text=message_text,
			parse_mode="HTML"
	)

@router.callback_query(F.data == "change_executor")
async def change_executor_handler(callback: CallbackQuery, state: FSMContext):
	processed_tasks = await get_processed_tasks(user_id=callback.from_user.id)
	await state.set_state(ExecutorsTask.task_id)
	result_text = "<u>📋 Ваши задачи:</u>\n\n"
	formatted_tasks = []
	for task in processed_tasks:
		task_info = (
			f"🆔 ID задачи: {task.id}\n"
			f"📌 <b>Задача:</b> {htd.quote(task.task_description)}\n"
			f"📅 <b>Создана:</b> {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏰ <b>Дедлайн:</b> {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"📊 <b>Статус:</b> {task.status.capitalize()}\n"
		)
		if task.file_id:
			task_info += f"📎 <b>Файл:</b> Прикреплен\n"
		formatted_tasks.append(task_info)
	
	result_text += "\n".join(formatted_tasks)
	await callback.message.answer(
		text=result_text,
		parse_mode="HTML",
		reply_markup=await processed_tasks_keyboard(tasks=processed_tasks)
	)

@router.callback_query(ExecutorsTask.task_id, F.data.startswith("change_task_ex"))
async def set_team(callback: CallbackQuery, state: FSMContext):
	task_id = int(callback.data.split(":")[1])
	await state.update_data(task_id=task_id)
	teams = await get_team_executors(user_id=callback.from_user.id)
	if not teams:
		await callback.message.answer("🤔 Вы не создали ни одной команды")
		return
	await callback.message.answer(text=f"👥 Выберите команду", reply_markup=await team_choose_keyboard(teams))
	await state.set_state(ExecutorsTask.team_id)

@router.callback_query(ExecutorsTask.team_id, F.data.startswith("team_ex"))
async def set_executors(callback: CallbackQuery, state: FSMContext):
	team_id = int(callback.data.split(":")[1])
	await state.update_data(team_id=team_id)
	executors = await get_executors_from_team(team_id=team_id)
	if not executors:
		await callback.message("🤔 Исполнителей нет либо они не готовы сейчас принимать задания")
		await state.clear()
		return
	await callback.message.answer(text="Выберите нового исполнителя", reply_markup=await executor_choose_keyboard(executors=executors, team_id=team_id, is_init=True))
	await state.set_state(ExecutorsTask.executors)

@router.callback_query(ExecutorsTask.executors, F.data.startswith("executor"))
async def choose_executors(callback: CallbackQuery, state: FSMContext):
	new_executor = callback.data.split(":")[1]
	team_id = int(callback.data.split(":")[2])
	data = await state.get_data()
	executors = await get_executors_from_team(team_id=team_id)
	if not executors:
		await callback.message("🤔 Исполнителей нет либо они не готовы сейчас принимать задания")
		await state.clear()
		return
	selected_executors = data.get("executors") if data.get("executors") else []
	selected_executors.append(new_executor)
	filtered_executors = [i for i in executors if i.username not in selected_executors] if selected_executors else executors
	await state.update_data(executors=selected_executors)
	await callback.message.answer(text="Выберите нового исполнителя", reply_markup=await executor_choose_keyboard(executors=filtered_executors, team_id=team_id))

@router.callback_query(ExecutorsTask.executors, F.data == "save_executors")
async def save_executors(callback: CallbackQuery, state: FSMContext):
	data = await state.get_data()
	[updated_processed_task, existing_executors] = await update_executors_in_task(new_executors_usernames=data.get("executors"), task_id=int(data.get("task_id")))
	await state.clear()

	new_executors_list = ", ".join([f"@{executor.username}" for executor in updated_processed_task.executors])
	message_text = (
		f"✅ <b>Исполнители успешно добавлены!</b>\n\n"
		f"📝 Задача: <i>{htd.quote(updated_processed_task.task_description)}</i>\n"
		f"👥 Новые исполнители: {new_executors_list}\n"
		f"⏰ Дедлайн: {updated_processed_task.expire_at.strftime('%d.%m.%Y %H:%M')}\n\n"
		f"Новые исполнители теперь могут приступить к работе. Удачи! 🚀\n\n"
	)
	if existing_executors:
		message_text += "🤷‍♂️ Не удалось добавить некоторых исполнителей так как они были добавлены к задаче ранее:\n"
		message_text += "\n".join([f"- @{executor}" for executor in existing_executors])
	await callback.message.answer(
		text=message_text,
		parse_mode="HTML"
	)

@router.callback_query(F.data == "change_time")
async def change_time_handler(callback: CallbackQuery):
	await callback.message.answer("change_time")

@router.callback_query(F.data == "assigned_tasks")
async def assigned_tasks_handler(callback: CallbackQuery):
	assigned_tasks = await get_assigned_tasks(user_id=callback.from_user.id)
	if not assigned_tasks:
		await callback.message.answer("🤷‍♂️ Вы еще не поставили ни одной задачи.")
		return
	text = htd.bold("📝 Ваши активные задачи:\n\n")
	for task in assigned_tasks:
			task_text = (
				f"🆔 ID задачи: {task.id}\n"
				f"⏰ Дата создания: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
				f"⏳ Срок выполнения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
				f"📋 Описание: {task.task_description}\n"
				f"🔄 Статус: {htd.code(task.status)}{status_emoji[task.status]}\n"
			)
			if task.executors:
				executors = ", ".join(
					f"{executor.first_name} {executor.last_name or ''} (@{executor.username})"
					for executor in task.executors
				)
				task_text += f"👥 Исполнители: {executors}\n"
			task_text += "\n" + "-" * 30 + "\n"
			text += task_text
	await callback.message.answer(text, parse_mode="HTML")

@router.callback_query(F.data == "all_tasks")
async def all_tasks_handler(callback: CallbackQuery):
	all_tasks = await get_all_tasks(user_id=callback.from_user.id)
	if not all_tasks:
		await callback.message.answer("🤷‍♂️ Вы еще ни разу не поставили задачу.")
		return
	text = htd.bold("📋 Все ваши задачи:\n\n")
	for task in all_tasks:
		task_text = (
			f"🆔 ID задачи: {task.id}\n"
			f"⏰ Дата создания: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏳ Срок выполнения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"📋 Описание: {task.task_description}\n"
			f"🔄 Статус: {htd.code(task.status)}{status_emoji[task.status]}\n"
		)
		if task.executors:
			executors = ", ".join(
				f"{executor.first_name} {executor.last_name or ''} (@{executor.username})"
				for executor in task.executors
			)
			task_text += f"👥 Исполнители: {executors}\n"
		task_text += "\n" + "-" * 30 + "\n"
		text += task_text
	await callback.message.answer(text, parse_mode="HTML")

@router.callback_query(F.data == "change_status")
async def change_status_handler(callback: CallbackQuery):
	try:
		status = await change_status(user_id=callback.from_user.id)
		image = "active_status" if status else "passive_status"
		message_text = (
			"✅ Ваш статус успешно изменен на *Активный*!\n\n"
			"Вы теперь доступны для выполнения задач и заказчики могут выдавать вам задание.\n"
			"Если что-то пойдет не так, вы всегда можете обратиться за помощью.\n\n"
			"Желаем удачи!"
    ) if status else (
			"🔕 Ваш статус успешно изменен на *Неактивный*.\n\n"
			"Вы временно недоступны для выполнения задач и невидимы для заказчиков.\n"
			"Мы сохраняем ваши данные и будем ждать, когда вы решите снова поменять статус на активный.\n\n"
			"Ждем вас с удовольствием"
		)
		await callback.message.answer_photo(
			photo=FSInputFile(f"./app/images/{image}.jpg"),
			caption=message_text,
			parse_mode="Markdown"
		)
	except Exception as exc:
		await callback.message.answer(f"[-] Error with change status: {exc}")

@router.callback_query(F.data == "create_team")
async def enter_team_name(callback: CallbackQuery, state: FSMContext):
	await callback.message.answer("🧑🏼‍💻 Please enter a name of your new team")
	await state.set_state(NewTeam.team_name)

@router.message(NewTeam.team_name)
async def enter_executors(message: Message, state: FSMContext):
	await state.update_data(team_name=message.text.strip().lower().capitalize())
	await message.answer("✍🏻👥 Пожалуйста введите username ваших исполнителей ( без @, через запятую и без пробелов ). Если пока что у вас нет готовых исполнителей, просто напишите точку и отправьте")
	await state.set_state(NewTeam.executors_username)

@router.message(NewTeam.executors_username)
async def create_team_handler(message: Message, state: FSMContext):
	if message.text != ".":
		executors_username = message.text.strip().split(",")
	else:
		executors_username = "."
	await state.update_data(executors_username=executors_username)
	await save_team(message, state)

async def save_team(message: Message, state: FSMContext):
	data = await state.get_data()
	[new_team, failed_executors, creator] = await create_team(creator_id=message.from_user.id, team_name=data.get("team_name"), executors_username=data.get("executors_username"))
	message_text = (
		f"<b>🎉 Команда {new_team.name} успешно создана! 🎉</b>\n\n"
		f"👑 Заказчик: @{creator.username}\n"
		f"👥 Исполнители:\n"
	)
	if data.get("executors_username") != ".":
		message_text += "\n".join([f"- <a href='https://t.me/{username}'>@{username}</a>" for username in data.get("executors_username") if username != message.from_user.username])
	else:
		message_text += "Исполнители пока не назначены."
	if failed_executors:
		message_text += "\n❌ Не удалось добавить некоторых пользователей: "
		for i in failed_executors:
			message_text += f"\n\n👤 Пользователь с username {i} не найден"
		message_text += "\n⚠️ Проверьте, правильно ли вы ввели username пользователя и зарегистрирован ли он вообще. \n➕ Добавьте нового пользователя в меню"
	await message.answer(text=message_text, parse_mode="HTML")
	await state.clear()

#? 100% - УДАЛЕНИЕ ЗАДАЧИ, ИЗМЕНЕНИЕ ИСПОЛНИТЕЛЕЙ ( ДОБАВЛЕНИЕ, УДАЛЕНИЕ, СМЕНА ), ПРИВЯЗКА ФАЙЛОВ, КАРТИНОК И ТД К ЗАДАЧАМ
#? 50%/50% -  ПОДТВЕРЖДЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ ПРИ ПОЛУЧЕНИИ ЗАДАЧИ

@router.message(Command("all_executors"))
async def all_executors_command(message: Message):
	teams = await get_teams_as_creator(creator_id=message.from_user.id)
	if not teams:
		await message.answer("⚠️ Вы еще не создали ни одной команды.")
		return

	message_text = "📋 Список ваших команд:\n"
	for team in teams:
		message_text += (
			f"📋 Команда: *{team.name}*\n"
			f"👑 Заказчик: {htd.link(f'@{team.creator.username}', f'tg://user?id={team.creator.telegram_id}')}\n"
			f"👥 Исполнители:\n"
		)
		if team.executors:
			for executor in team.executors:
				message_text += (
					f"- {htd.link(f'@{executor.username}', f'tg://user?id={executor.telegram_id}')} - статус: {'😎 Активен' if executor.status else '😴 Не активен'}\n"
				)
		else:
			message_text += "Исполнители пока не назначены.\n"
		message_text += "\n" + "-" * 30 + "\n"

	await message.answer(text=message_text, parse_mode="HTML")

@router.message(Command("create_task"))
async def set_task_handler(message: Message, state: FSMContext):
	await message.answer("Введите описание задачи:")
	await state.set_state(NewTask.task_description)

@router.message(Command("confirm_task"))
async def confirm_task_handler(message: Message):
	tasks_as_creator = await get_processed_tasks(user_id=message.from_user.id)
	if not tasks_as_creator:
		await message.answer("⚠️ У вас нет активных задач для закрытия.")
		return

	message_text = "📋 Список ваших активных задач:\n"
	for task in tasks_as_creator:
		message_text += (
			f"📝 Задача #{task.id}\n"
			f"📅 Создана: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏰ Срок выполнения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"💬 Описание: {task.task_description}\n"
		)

	task_ids = [str(i.id) for i in tasks_as_creator]
	await message.answer(
		text=message_text,
		reply_markup=await confirm_task_keyboard(task_ids=task_ids)
	)

@router.message(Command("change_executors"))
async def change_executor_handler(message: Message, state: FSMContext):
	processed_tasks = await get_processed_tasks(user_id=message.from_user.id)
	await state.set_state(ExecutorsTask.task_id)

	result_text = "<u>📋 Ваши задачи:</u>\n"
	formatted_tasks = []
	for task in processed_tasks:
		task_info = (
			f"🆔 ID задачи: {task.id}\n"
			f"📌 <b>Задача:</b> {htd.quote(task.task_description)}\n"
			f"📅 <b>Создана:</b> {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏰ <b>Дедлайн:</b> {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"📊 <b>Статус:</b> {task.status.capitalize()}\n"
		)
		if task.file_id:
			task_info += f"📎 <b>Файл:</b> Прикреплен\n"
		formatted_tasks.append(task_info)

	result_text += "\n".join(formatted_tasks)
	await message.answer(
		text=result_text,
		parse_mode="HTML",
		reply_markup=await processed_tasks_keyboard(tasks=processed_tasks)
	)
@router.message(Command("my_tasks"))
async def get_user_tasks_handler(message: Message):
	tasks = await get_user_tasks(user_id=int(message.from_user.id))
	if not tasks:
		await message.answer("⚠️ У вас нет активных задач.")
		return

	message_text = "📋 <b>Список ваших задач:</b>\n"
	for task in tasks:
		urgency_status = "🚨 СРОЧНО, осталось меньше дня для выполнения" if task.expire_at.date() == datetime.now().date() else "⏳ В процессе"
		message_text += (
			f"<b>Задача #{task.id}</b>\n"
			f"📅 Создана: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏰ Срок завершения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"📝 Описание: {task.task_description}\n"
		)
		if task.expire_at.date() == datetime.now().date():
			message_text += f"❗️ {urgency_status}\n"
		message_text += "\n" + "-" * 30 + "\n"

	await message.answer(text=message_text, parse_mode="HTML")

@router.message(Command("assigned_tasks"))
async def assigned_tasks_handler(message: Message):
	assigned_tasks = await get_assigned_tasks(user_id=message.from_user.id)
	if not assigned_tasks:
		await message.answer("🤷‍♂️ Вы еще не поставили ни одной задачи.")
		return

	text = htd.bold("📝 Ваши активные задачи:\n")
	for task in assigned_tasks:
		task_text = (
			f"🆔 ID задачи: {task.id}\n"
			f"⏰ Дата создания: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏳ Срок выполнения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"📋 Описание: {task.task_description}\n"
			f"🔄 Статус: {htd.code(task.status)}{status_emoji[task.status]}\n"
		)
		if task.executors:
			executors = ", ".join(
				f"{executor.first_name} {executor.last_name or ''} (@{executor.username})"
				for executor in task.executors
			)
			task_text += f"👥 Исполнители: {executors}\n"
		task_text += "\n" + "-" * 30 + "\n"
		text += task_text

	await message.answer(text, parse_mode="HTML")

@router.message(Command("all_tasks"))
async def all_tasks_handler(message: Message):
	all_tasks = await get_all_tasks(user_id=message.from_user.id)
	if not all_tasks:
		await message.answer("🤷‍♂️ Вы еще ни разу не поставили задачу.")
		return

	text = htd.bold("📋 Все ваши задачи:\n")
	for task in all_tasks:
		task_text = (
			f"🆔 ID задачи: {task.id}\n"
			f"⏰ Дата создания: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"⏳ Срок выполнения: {task.expire_at.strftime('%d.%m.%Y %H:%M')}\n"
			f"📋 Описание: {task.task_description}\n"
			f"🔄 Статус: {htd.code(task.status)}{status_emoji[task.status]}\n"
		)
		if task.executors:
			executors = ", ".join(
				f"{executor.first_name} {executor.last_name or ''} (@{executor.username})"
				for executor in task.executors
			)
			task_text += f"👥 Исполнители: {executors}\n"
		task_text += "\n" + "-" * 30 + "\n"
		text += task_text

	await message.answer(text, parse_mode="HTML")
	
@router.message(Command("change_status"))
async def change_status_handler(message: Message):
	try:
		status = await change_status(user_id=message.from_user.id)
		image = "active_status" if status else "passive_status"
		message_text = (
			"✅ Ваш статус успешно изменен на *Активный*!\n"
			"Вы теперь доступны для выполнения задач и заказчики могут выдавать вам задание.\n"
			"Если что-то пойдет не так, вы всегда можете обратиться за помощью.\n"
			"Желаем удачи!"
		) if status else (
			"🔕 Ваш статус успешно изменен на *Неактивный*.\n"
			"Вы временно недоступны для выполнения задач и невидимы для заказчиков.\n"
			"Мы сохраняем ваши данные и будем ждать, когда вы решите снова поменять статус на активный.\n"
			"Ждем вас с удовольствием"
		)
		await message.answer_photo(
			photo=FSInputFile(f"./app/images/{image}.jpg"),
			caption=message_text,
			parse_mode="Markdown"
		)
	except Exception as exc:
		await message.answer(f"[-] Error with change status: {exc}")

@router.message(Command("create_team"))
async def enter_team_name(message: Message, state: FSMContext):
	await message.answer("🧑🏼‍💻 Please enter a name of your new team")
	await state.set_state(NewTeam.team_name)

@router.message(Command("change_team"))
async def change_team_handler(message: Message, state: FSMContext):
	teams = await get_team_executors(user_id=message.from_user.id)
	if not teams:
		await message.answer("🤔 Вы не создали ни одной команды")
		return
	await message.answer(text=f"👥 Выберите команду", reply_markup=await team_choose_keyboard(teams))
	await state.set_state(AddTeam.team_id)