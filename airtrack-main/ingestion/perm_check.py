import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_WRITER_USER"),
    password=os.getenv("DB_WRITER_PASSWORD"),
)
cursor = conn.cursor()

# 1. SELECT should work
cursor.execute("SELECT COUNT(*) FROM reading")
print("SELECT works. Rows:", cursor.fetchone()[0])

# 2. DELETE should be refused
try:
    cursor.execute("DELETE FROM reading")
    print("PROBLEM: delete was allowed!")
except mysql.connector.Error as err:
    print("DELETE refused, as expected:", err)

conn.rollback()
cursor.close()
conn.close()