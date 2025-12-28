import os
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Default configuration
MYSQL_HOST = os.getenv("MYSQL_HOST", "")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "")

def get_connection():
    """
    Get a pymysql connection.
    Remember to close the connection after use.
    """
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=DictCursor,
        autocommit=True  # Important for LangGraph checkpointers
    )

def get_connection_params():
    """
    Return connection parameters as a dictionary.
    Useful for connection pools if needed.
    """
    return {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "database": MYSQL_DATABASE,
        "cursorclass": DictCursor,
        "autocommit": True
    }
