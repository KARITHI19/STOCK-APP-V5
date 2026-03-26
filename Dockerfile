FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV MPLBACKEND=Agg
ENV PORT=8080
ENV APP_ENTRYPOINT=app.py

RUN python -m pip install --upgrade pip

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY . /app

EXPOSE 8080

CMD ["sh", "-c", "streamlit run ${APP_ENTRYPOINT} --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true"]
