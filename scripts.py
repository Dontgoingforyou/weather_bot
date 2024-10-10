import psycopg2
from psycopg2 import sql

def create_database(db_name):
    connection = psycopg2.connect(user="your_username", password="your_password", host="localhost")
    connection.autocommit = True
    cursor = connection.cursor()

    # Создаем базу данных
    cursor.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(db_name)))
    print(f"Database '{db_name}' created successfully!")

    cursor.close()
    connection.close()

def create_table(db_name):
    connection = psycopg2.connect(user="your_username", password="your_password", host="localhost", database=db_name)
    cursor = connection.cursor()

    # Создаем таблицу logs
    create_table_query = """
    CREATE TABLE logs (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        command TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        response TEXT
    );
    """
    cursor.execute(create_table_query)
    print("Table 'logs' created successfully!")

    cursor.close()
    connection.close()

def main():
    db_name = 'weather_bot_db'
    create_database(db_name)
    create_table(db_name)

if __name__ == "__main__":
    main()
