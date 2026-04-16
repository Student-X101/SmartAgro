FROM python:3.10-slim
# 1. Start with the root user to install system tools
USER root

# 2. Install ffmpeg (fixes the ffprobe error)
RUN apt-get update && apt-get install -y ffmpeg

# 3. Create the user if it doesn't exist and switch back (Hugging Face requirement)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:${PATH}"

# 4. Set the working directory
WORKDIR /app

# 5. Copy your files
COPY --chown=user . .

# 6. Now run pip (this will work now!)
RUN pip install --no-cache-dir -r requirements.txt

# 7. Start the app
CMD ["uvicorn", "agent_bot:app", "--host", "0.0.0.0", "--port", "8000"]


