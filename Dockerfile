# Use the official Python image as base
FROM python:3.11

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the port your app runs on (e.g., Flask default is 5000)
EXPOSE 8000

# Command to run the application
CMD ["python3", "agent.py", "start"]
