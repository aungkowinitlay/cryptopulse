# Use official Python image as base
   FROM python:3.9-slim

   # Set working directory
   WORKDIR /app

   # Copy requirements and install dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Install Nginx
   RUN apt-get update && apt-get install -y nginx

   # Copy project files
   COPY . .

   # Copy Nginx configuration
   COPY nginx.conf /etc/nginx/sites-available/default

   # Expose port 80
   EXPOSE 80

   # Start script for Nginx and Gunicorn
   CMD ["sh", "-c", "nginx && gunicorn --bind 0.0.0.0:8000 app:app"]