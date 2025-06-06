from celery import Celery
from celery.contrib.abortable import AbortableTask

from app.requests import stop_task
from config import settings

import requests
import asyncio

app = Celery(__name__)
app.conf.broker_url = "redis://redis:6379/0"
app.conf.result_backend = "redis://redis:6379/0"

@app.task(name="create_task", base=AbortableTask)
def confirm_task(task_data):
	loop = asyncio.get_event_loop()
	print(task_data)
	if not confirm_task.is_aborted():
		loop.run_until_complete(stop_task(task_id=task_data.get("id"), status="canceled"))
		print("[!] Canceled task")
		return "successful"
	# loop.run_until_complete(stop_task(task_id=task_data.get("id"), status="completed"))
	# print("[+] Completed task")
	# return None

@app.task(name="notificate", base=AbortableTask)
def notificate_user(task_data):
	if not notificate_user.is_aborted():
		notification_text = (
			f"⚠️ 'Внимание! До завершения задачи осталось 5 минут!'\n\n"
			f"🆔 ID задачи: {task_data.get("id")}\n"
			f"📋 Описание: {task_data.get("task_description")}\n"
			f"⏳ Срок выполнения: {task_data.get("expire_at")}\n"
			f"🔄 Текущий статус: {task_data.get("status")}\n\n"
			f"🔥 У вас есть последняя возможность завершить задачу или попросить увеличить дедлайн!"
		)
		for executor_id in task_data.get("executors_id"):
			requests.get(f"{settings.BOT_API_URL}{settings.BOT_TOKEN}/sendMessage?chat_id={executor_id}&text={notification_text}")
		return None
	# print("[-] Notificate is not require")
	# return None

#! В ИДЕАЛЕ, чтобы сразу по две таски не было ожидаемых, сначала прогнать одну для notification, выполнить и поставить другую, уже на удаление, но мне лень, похуй и тд