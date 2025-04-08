# Use an official lightweight Python 3.12 image.
FROM python:3.12-slim

# Prevents Python from writing .pyc files to disk.
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout and stderr.
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file and install Python dependencies.
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the rest of your application code into the container.
COPY . /app/

# Expose port 5000 (this is the port your Flask app will run on).
EXPOSE 5000

# Start the application using Gunicorn.
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
