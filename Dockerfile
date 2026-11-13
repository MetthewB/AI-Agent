FROM python:3.15-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY multi_agents.py .

CMD ["python", "multi_agents.py"]