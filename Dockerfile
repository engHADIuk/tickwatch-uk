FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY frontend ./frontend
ENV TICK_DB_PATH=/srv/data/ticks.db TICK_SNAPSHOT_PATH=/srv/data/snapshot.json
VOLUME /srv/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
