FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN useradd --uid 10001 --create-home community
USER community
EXPOSE 8000
CMD ["uvicorn", "community_backend.app:create_app", "--factory", "--host", "0.0.0.0", "--workers", "1"]
