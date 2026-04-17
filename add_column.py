import psycopg2

try:
    conn = psycopg2.connect(
        host="db.ddoqvbsmuhuyrfxroexc.supabase.co",
        database="postgres",
        user="postgres",
        password="RadhaKrishna@123",
        port=5432
    )
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE repositories ADD COLUMN IF NOT EXISTS repo_summary TEXT;")
    print("Successfully added repo_summary column")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
