import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="bi_agent_demo",
        user="postgres",
        password="123"
    )
    print("✅ Kết nối thành công!")
    
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print(cur.fetchone())
    
    cur.close()
    conn.close()
except Exception as e:
    print("❌ Kết nối thất bại:", e)