from database import get_connection

try:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT USER FROM DUAL")
            result = cursor.fetchone()

            print("Oracle Database Connected Successfully!")
            print("Connected User:", result[0])

            cursor.execute("""
                SELECT table_name
                FROM user_tables
                ORDER BY table_name
            """)

            print("\nAvailable Tables:")

            for row in cursor:
                print(row[0])

except Exception as error:
    print("Database Connection Failed!")
    print("Error:", error)