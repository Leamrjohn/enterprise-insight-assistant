"""生成可复现的经营模拟数据

每次运行生成完全相同的数据（random.seed(42)）。
"""

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

# ── 建表 ──────────────────────────────────

cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        region TEXT NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        price NUMERIC(10, 2) NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        order_date DATE NOT NULL,
        total_amount NUMERIC(12, 2) NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id SERIAL PRIMARY KEY,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        quantity INTEGER NOT NULL,
        unit_price NUMERIC(10, 2) NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id SERIAL PRIMARY KEY,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        complaint_date DATE NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL
    )
""")

print("建表完成")

# ── 填充 customers ─────────────────────────

customers = [
    ("星耀科技", "华东"), ("明辉电子", "华东"), ("鹏程物流", "华东"),
    ("博雅软件", "华东"), ("永信商贸", "华东"),
    ("华远集团", "华南"), ("天元科技", "华南"), ("金盛实业", "华南"),
    ("佳和贸易", "华南"), ("恒达精密", "华南"),
    ("北方重工", "华北"), ("瑞丰能源", "华北"), ("正大建材", "华北"),
    ("新力机械", "华北"), ("安泰化工", "华北"),
    ("西南航空", "西南"), ("天府农业", "西南"), ("云岭药业", "西南"),
    ("滇池旅游", "西南"), ("巴蜀食品", "西南"),
]

cur.executemany(
    "INSERT INTO customers (name, region) VALUES (%s, %s)",
    customers,
)
cur.execute("DELETE FROM customers WHERE id > 20")

print("customers 填充完成")

# ── 填充 products ──────────────────────────

products = [
    ("智能手机X1", "电子", 3999.00),
    ("笔记本电脑Pro", "电子", 7999.00),
    ("无线耳机", "电子", 599.00),
    ("智能手表", "电子", 1299.00),
    ("羽绒服", "服装", 899.00),
    ("运动鞋", "服装", 459.00),
    ("商务衬衫", "服装", 299.00),
    ("有机大米", "食品", 89.00),
    ("进口奶粉", "食品", 268.00),
    ("坚果礼盒", "食品", 158.00),
]

cur.executemany(
    "INSERT INTO products (name, category, price) VALUES (%s, %s, %s)",
    products,
)

print("products 填充完成")

# ── 填充 orders + order_items ─────────────

n_customers = 20
n_products = 10
start_date = date(2024, 1, 1)
end_date = date(2024, 12, 31)
total_days = (end_date - start_date).days

all_orders = []       # 收集所有订单 (customer_id, order_date, total_amount)
all_items = []        # 收集所有订单明细 (order_id, product_id, quantity, unit_price)

for day_offset in range(total_days):
    current_date = start_date + timedelta(days=day_offset)

    # ── 异常注入：华东区最大客户（id=1，星耀科技）
    #    8月1日之后不再下单（模拟客户流失）
    # ──────────────────────────────────────────
    if current_date >= date(2024, 8, 1):
        active_customers = [cid for cid in range(2, n_customers + 1)]
    else:
        active_customers = list(range(1, n_customers + 1))

    # 每天随机 1～2 个客户下单
    num_orders_today = random.choice([1, 1, 1, 2])
    buyers = random.sample(active_customers, min(num_orders_today, len(active_customers)))

    for cid in buyers:
        # 每个订单买 1～3 种商品
        num_items = random.choice([1, 1, 2, 2, 3])
        picked_products = random.sample(range(1, n_products + 1), num_items)

        order_total = 0.0
        for pid in picked_products:
            qty = random.randint(1, 5)
            # 从 products 列表中查价格（pid-1 是因为列表索引从 0 开始）
            unit_price = float(products[pid - 1][2])
            all_items.append((len(all_orders) + 1, pid, qty, unit_price))
            order_total += qty * unit_price

        all_orders.append((cid, current_date, round(order_total, 2)))

# 批量插入 orders
cur.executemany(
    "INSERT INTO orders (customer_id, order_date, total_amount) VALUES (%s, %s, %s)",
    all_orders,
)

# 批量插入 order_items
cur.executemany(
    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
    all_items,
)

print(f"orders 填充完成 ({len(all_orders)} 条), order_items 填充完成 ({len(all_items)} 条)")

# ── 填充 complaints ────────────────────────

complaints_data = []

# 正常月份：1～5 月和 7～12 月，每月 2～3 条客诉
for month in [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]:
    for _ in range(random.randint(2, 3)):
        order_id = random.randint(1, len(all_orders))
        day = random.randint(1, 28)
        complaints_data.append((
            order_id,
            date(2024, month, day),
            random.choice(["产品质量", "物流延误", "客服态度"]),
            random.choice(["low", "medium"]),
        ))

# ── 异常注入：6月客诉暴增 ──────────────────
#    电子类产品质量问题，严重度高
# ──────────────────────────────────────────
for _ in range(10):
    order_id = random.randint(1, len(all_orders))
    day = random.randint(1, 28)
    complaints_data.append((
        order_id,
        date(2024, 6, day),
        "产品质量",
        "high",
    ))

cur.executemany(
    "INSERT INTO complaints (order_id, complaint_date, category, severity) VALUES (%s, %s, %s, %s)",
    complaints_data,
)

print(f"complaints 填充完成 ({len(complaints_data)} 条)")

# ── 验证 ──────────────────────────────────

cur.execute("SELECT COUNT(*) FROM orders")
row = cur.fetchone()
print(f"验证：orders 总数 = {row[0] if row is not None else 0}")

cur.execute("""
    SELECT TO_CHAR(complaint_date, 'YYYY-MM') AS month, COUNT(*)
    FROM complaints
    GROUP BY month
    ORDER BY month
""")
print("验证：各月客诉数量：")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} 条")

cur.execute("""
    SELECT region, COUNT(*) AS order_count
    FROM orders JOIN customers ON orders.customer_id = customers.id
    WHERE order_date >= '2024-08-01'
    GROUP BY region
    ORDER BY region
""")
print("验证：8月起各区域订单数：")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} 条")

cur.close()
conn.close()
print("\n全部完成")
