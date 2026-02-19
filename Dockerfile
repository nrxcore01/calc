FROM python:3.10

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DO NOT set API_TOKEN manually here  
# Railway automatically injects environment variables at runtime

CMD ["python", "main.py"]
