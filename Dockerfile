FROM python:latest

WORKDIR /bot-app
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "main.py" ]