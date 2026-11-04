FROM python:3-alpine
WORKDIR /app
RUN pip install --no-cache-dir "pg8000>=1.31,<2"
COPY app.py seed.py ./
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8766
CMD ["python", "app.py"]
