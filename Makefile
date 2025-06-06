stop_services:
	systemctl stop postgresql.service
	systemctl stop redis-server.service

clean_qwe:
	@if ["$(shell docker ps -aq)"]; then \
		docker rm -f $(shell docker ps -aq); \
	fi

build:
	docker-compose build

clean:
	docker system prune --force
	docker container prune --force
	docker volume prune --force
	docker-compose down

up:
	docker-compose up

pg:
	docker exec -it postgres_bot psql -U postgres

rs:
	docker exec -it redis_bot redis-cli

bot:
	docker exec -it task_tracker_app_1 bash

all: stop_services clean build up