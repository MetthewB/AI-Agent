# Use a lightweight Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your python script into the container
COPY agent_with_memory.py .

# The command to run when the container starts
CMD ["python", "agent_with_memory.py"]