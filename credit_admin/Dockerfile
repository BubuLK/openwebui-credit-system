FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY . /app

# Build and install the project using pip and pyproject.toml
# Install build tools then install the package (which will build wheels and dependencies)
RUN python -m pip install --no-cache-dir build && \
	python -m build --wheel && \
	python -m pip install --no-cache-dir dist/*.whl

# Set default command to run the FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
