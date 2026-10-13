import os
import oracledb

def get_connection():
    return oracledb.connect(
        user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
                dsn=os.environ.get("DB_DSN", "localhost:1521/XEPDB1")
    )
