from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

async def main_keyboard(user_data) -> InlineKeyboardMarkup:
	builder = InlineKeyboardBuilder()
	builder.add(
		InlineKeyboardButton(text="👥 Посмотреть исполнителей", callback_data="all_executors"),
		InlineKeyboardButton(text="📝 Назначить задачу и исполнителя", callback_data="set_task"),
		InlineKeyboardButton(text="✅ Снять задачу", callback_data="confirm_task"),
		InlineKeyboardButton(text="🔄 Изменить исполнителя задачи", callback_data="change_executor"),
		# InlineKeyboardButton(text="⌛ Изменить время выполнения задачи", callback_data="change_time"),
		InlineKeyboardButton(text="📔 Мои задачи", callback_data="my_tasks"),
		InlineKeyboardButton(text="📝 Поставленные задачи", callback_data="assigned_tasks"),
		InlineKeyboardButton(text="📚 Все задачи", callback_data="all_tasks"),
		InlineKeyboardButton(text=f"{"😎" if user_data.status == True else "😶‍🌫️"} Сменить статус на {"Активный" if user_data.status == False else "Неактивный"} ", callback_data="change_status"),
		InlineKeyboardButton(text="✍️ Создать команду", callback_data="create_team"),
		InlineKeyboardButton(text="✍️ Изменить команду", callback_data="change_team"),
	)
	return builder.adjust(2).as_markup(resize_keyboard=True, one_time_keyboard=True)

async def confirm_task_keyboard(task_ids: list[str]):
	builder = InlineKeyboardBuilder()
	for task_id in task_ids:
		builder.add(
			InlineKeyboardButton(
				text=f"Закрыть задачу под id: {task_id}",
				callback_data=f"close_task:{task_id}"
			)
		)
	return builder.adjust(2).as_markup(resize_keyboard=True, one_time_keyboard=True)

async def team_choose_keyboard(teams):
	builder = InlineKeyboardBuilder()
	for team in teams:
		builder.add(
			InlineKeyboardButton(
				text=f"Команда: {team.name}",
				callback_data=f"team_ex:{team.id}"
			)
		)
	return builder.adjust(2).as_markup(resize_keyboard=True, one_time_keyboard=True)

async def executor_choose_keyboard(executors, team_id: int, is_init: bool = False):
	builder = InlineKeyboardBuilder()
	for executor in executors:
		builder.add(
			InlineKeyboardButton(
				text=f"Исполнитель: {executor.username}",
				callback_data=f"executor:{executor.username}:{team_id}"
			)
		)
	if not is_init:
		builder.add(InlineKeyboardButton(
			text="💾 Сохранить",
			callback_data="save_executors"
		))
	return builder.adjust(2).as_markup(resize_keyboard=True, one_time_keyboard=True)

async def processed_tasks_keyboard(tasks):
	builder = InlineKeyboardBuilder()
	for task in tasks:
		builder.add(
			InlineKeyboardButton(
				text=f"Задача - #{task.id}",
				callback_data=f"change_task_ex:{task.id}"
			)
		)
	return builder.adjust(2).as_markup(resize_keyboard=True, one_time_keyboard=True)