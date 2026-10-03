FROM python:3.12-slim
WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home pcl && mkdir /data && chown pcl /data
COPY app ./app
COPY config ./config
USER pcl
ENV DATABASE_PATH=/data/pcl.sqlite3
EXPOSE 8080
# One process for single-volume SQLite; threads serve quick webhooks while API calls run.
CMD ["gunicorn","--bind","0.0.0.0:8080","--workers","1","--threads","4","--timeout","60","--access-logfile","/dev/null","app.server:application"]
