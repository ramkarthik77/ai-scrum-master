FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[web,openai]" && useradd -m app
USER app

EXPOSE 8000
# Single worker: sessions are held in memory.
CMD ["uvicorn", "scrum_agent.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
