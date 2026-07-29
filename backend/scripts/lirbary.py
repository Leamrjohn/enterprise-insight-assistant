import random
from datetime import date, timedelta
import psycopg

random.seed(42)

conn = psycopg.connect(
    host="127.0.0.1",
    port=5434,
    user="business_app",
    password="business_password",
    dbname="business_data",
)

conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS readers (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        school TEXT NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        class TEXT NOT NULL,
        chubanshe TEXT NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS borrow_records (
        id SERIAL PRIMARY KEY,
        reader_id INTEGER NOT NULL REFERENCES readers(id),
        book_id INTEGER NOT NULL REFERENCES books(id),
        borrow_date DATE NOT NULL,
        return_date DATE
    )
""")

readers = [("王一", "计算机"), ("刘二", "医学"), ("张三", "化学")]
cur.executemany(
    "INSERT INTO readers (name, school) VALUES (%s, %s)",
    readers,
)

books = [("Python编程", "一类", "北京"), ("2", "一类", "南京"), ("3", "二类", "北京")]
cur.executemany(
    "INSERT INTO books (name, class, chubanshe) VALUES (%s, %s, %s)",
    books,
)

print("建表 + readers + books 填充完成")

n_readers = len(readers)
n_books = len(books)
start_date = date(2024, 3, 1)
end_date = date(2024, 12, 31)
total_days = (end_date - start_date).days

borrow_records = []

for day_offset in range(total_days):
    current_date = start_date + timedelta(days=day_offset)

    # 异常1：信息学院（读者id=1，王一）9月后不再借书
    if current_date >= date(2024, 9, 1):
        active_readers = list(range(2, n_readers + 1))  # [2, 3]
    else:
        active_readers = list(range(1, n_readers + 1))  # [1, 2, 3]

    active_books = list(range(1, n_books + 1))  # [1, 2, 3]

    # 今天借几条
    num_today = random.choice([0, 1, 1, 2])
    if num_today > 0 and len(active_readers) > 0:
        selected = random.sample(active_readers, min(num_today, len(active_readers)))
    else:
        selected = []

    for rid in selected:
        bid = random.choice(active_books)
        return_date = current_date + timedelta(days=random.randint(7, 30))
        borrow_records.append((rid, bid, current_date, return_date))

# 异常2：《Python编程》（书id=1）被额外抢手15次
for _ in range(15):
    rid = random.choice(list(range(1, n_readers + 1)))
    day = start_date + timedelta(days=random.randint(0, total_days - 1))
    return_date = day + timedelta(days=random.randint(7, 30))
    borrow_records.append((rid, 1, day, return_date))

cur.executemany(
    "INSERT INTO borrow_records (reader_id, book_id, borrow_date, return_date) VALUES (%s, %s, %s, %s)",
    borrow_records,
)

print(f"borrow_records 填充完成 ({len(borrow_records)} 条)")
cur.close()
conn.close()
