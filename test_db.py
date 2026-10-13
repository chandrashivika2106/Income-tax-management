from database import get_connection

try:
    connection = get_connection()
    print("Oracle Database connected successfully!")

    cursor = connection.cursor()

    cursor.execute("SELECT USER FROM DUAL")
    print("Connected user:", cursor.fetchone()[0])

    cursor.execute("""
        SELECT TABLE_NAME
        FROM USER_TABLES
        ORDER BY TABLE_NAME
    """)

    print("\nAvailable tables:")

    for row in cursor:
        print("-", row[0])

except Exception as e:
    print("Database connection failed!")
    print("Error:", e)

finally:
    if "cursor" in locals():
        cursor.close()

    if "connection" in locals():
        connection.close()