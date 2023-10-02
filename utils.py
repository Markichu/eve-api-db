import psycopg2

def connect_to_db():
    conn = psycopg2.connect(
        host="localhost",
        database="eve",
        user="postgres",
        password="password"
    )
    return conn