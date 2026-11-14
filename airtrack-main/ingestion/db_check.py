import os
from dotenv import load_dotenv
import mysql.connector

# Load the values from .env (in the repo root, one folder above ingestion/)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_WRITER_USER"),
    password=os.getenv("DB_WRITER_PASSWORD"),
)

cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM reading")
count = cursor.fetchone()[0]
print("Connected as writer. Rows in reading:", count)

cursor.close()
conn.close()