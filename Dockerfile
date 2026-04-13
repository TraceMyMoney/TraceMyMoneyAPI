FROM python:3.11-slim
WORKDIR /app

# Install dependencies
COPY pyproject.toml .
COPY uv.lock .

RUN pip install uv
ENV UV_SYSTEM_PYTHON=1
RUN uv sync --no-cache

# Copy application
COPY ./app ./app
COPY main.py main.py

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
