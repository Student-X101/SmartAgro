# Use Python
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy your files into the container
COPY . .

# Install libraries
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port (Hugging Face uses 7860 by default)
EXPOSE 7860

# Run the app
CMD ["uvicorn", "agent_bot:app", "--host", "0.0.0.0", "--port", "7860"]