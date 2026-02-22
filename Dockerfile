FROM python:3.11-slim

# Install requests so the container can HTTP POST to your host's Ollama
RUN pip install requests

# Set up the working directory
WORKDIR /app

# Copy the Ollama bridge script into the container
COPY llm_query.py /app/llm_query.py

# Keep the container alive indefinitely so we can 'docker exec' into it
CMD ["tail", "-f", "/dev/null"]