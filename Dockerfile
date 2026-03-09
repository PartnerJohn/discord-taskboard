FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir discord.py==2.5.2
COPY . .
CMD ["python", "bot.py"]
