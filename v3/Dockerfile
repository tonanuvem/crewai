FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages directly
RUN pip install --no-cache-dir \
    streamlit \
    crewai \
    crewai-tools \
    langchain-google-genai \
    python-dotenv \
    python-docx \
    PyPDF2

# Copy application
COPY app.py .

# Create directories
RUN mkdir -p logs outputs

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
