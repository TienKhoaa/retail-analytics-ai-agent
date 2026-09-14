"""
Script sinh dữ liệu synthetic cho project Retail Analytics AI Agent.

Yêu cầu trước khi chạy:
    - Đã tạo database `bi_agent_demo` và chạy xong create_schema.sql
    - pip install faker psycopg2-binary numpy pandas

Cách chạy:
    python generate_data.py
"""

import os
import random
from datetime import datetime, timedelta

import numpy as np
import psycopg2
from dotenv import load_dotenv
from faker import Faker

load_dotenv()

# ============================================================
# CẤU HÌNH KẾT NỐI DATABASE — đọc từ file .env
# ============================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "bi_agent_demo"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}
if not DB_CONFIG["password"]:
    raise ValueError("Chưa tìm thấy DB_PASSWORD trong file .env")

# ============================================================
# THAM SỐ SỐ LƯỢNG DỮ LIỆU — có thể chỉnh để tạo nhiều/ít hơn
# ============================================================
NUM_CUSTOMERS = 300
NUM_PRODUCTS_PER_CATEGORY = 15
NUM_ORDERS = 2000
MAX_ITEMS_PER_ORDER = 5

# Khoảng thời gian dữ liệu đơn hàng (2 năm gần nhất) để thấy được xu hướng theo thời gian
START_DATE = datetime.now() - timedelta(days=730)
END_DATE = datetime.now()

fake = Faker("vi_VN")  # dùng locale Việt Nam cho tên/địa chỉ tự nhiên hơn
random.seed(42)
np.random.seed(42)

CATEGORIES = [
    "Điện tử", "Thời trang nam", "Thời trang nữ", "Gia dụng",
    "Thực phẩm", "Mỹ phẩm", "Sách & Văn phòng phẩm", "Đồ chơi trẻ em",
]

CITIES = [
    "Hồ Chí Minh", "Hà Nội", "Đà Nẵng", "Cần Thơ", "Hải Phòng",
    "Nha Trang", "Biên Hòa", "Vũng Tàu",
]

ORDER_STATUSES = ["completed", "completed", "completed", "pending", "cancelled", "returned"]
# lặp "completed" nhiều lần để tỷ lệ đơn hoàn tất chiếm đa số, giống thực tế


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def seasonal_weight(date: datetime) -> float:
    """
    Tạo hệ số mùa vụ: doanh số tăng vào tháng 11-12 (mua sắm cuối năm)
    và giảm nhẹ vào tháng 2 (sau Tết). Giúp dữ liệu có pattern thật hơn
    thay vì phân bố đều tuyệt đối.
    """
    month = date.month
    if month in (11, 12):
        return 1.6
    if month == 2:
        return 0.7
    if month in (6, 7):
        return 1.15  # mùa hè, mua sắm tăng nhẹ
    return 1.0


def random_date_weighted(start: datetime, end: datetime) -> datetime:
    """Sinh ngày ngẫu nhiên trong khoảng, có trọng số theo mùa vụ."""
    total_days = (end - start).days
    while True:
        candidate = start + timedelta(days=random.randint(0, total_days))
        weight = seasonal_weight(candidate)
        if random.random() < weight / 1.6:  # chuẩn hóa theo weight cao nhất
            return candidate


def generate_categories(cur):
    ids = []
    for name in CATEGORIES:
        cur.execute(
            "INSERT INTO categories (category_name) VALUES (%s) RETURNING category_id",
            (name,),
        )
        ids.append(cur.fetchone()[0])
    return ids


def generate_customers(cur, n):
    ids = []
    for _ in range(n):
        name = fake.name()
        city = random.choice(CITIES)
        signup_date = fake.date_between(start_date="-3y", end_date="today")
        cur.execute(
            """INSERT INTO customers (customer_name, city, signup_date)
               VALUES (%s, %s, %s) RETURNING customer_id""",
            (name, city, signup_date),
        )
        ids.append(cur.fetchone()[0])
    return ids


# Tên sản phẩm mẫu theo từng danh mục để dữ liệu có ý nghĩa thay vì random vô nghĩa
PRODUCT_NAME_TEMPLATES = {
    "Điện tử": ["Tai nghe bluetooth", "Sạc dự phòng", "Bàn phím cơ", "Chuột không dây",
                "Loa mini", "Ốp lưng điện thoại", "Cáp sạc nhanh", "Đèn LED bàn"],
    "Thời trang nam": ["Áo sơ mi nam", "Quần jeans nam", "Áo thun nam", "Giày sneaker nam",
                        "Thắt lưng da", "Áo khoác nam"],
    "Thời trang nữ": ["Đầm nữ", "Áo kiểu nữ", "Chân váy", "Túi xách nữ",
                       "Giày cao gót", "Áo len nữ"],
    "Gia dụng": ["Nồi cơm điện", "Máy xay sinh tố", "Bình giữ nhiệt", "Chảo chống dính",
                 "Máy lọc nước mini", "Bộ dao kéo bếp"],
    "Thực phẩm": ["Cà phê hòa tan", "Trà túi lọc", "Snack khoai tây", "Mì ăn liền cao cấp",
                  "Hạt điều rang muối", "Nước ép trái cây"],
    "Mỹ phẩm": ["Kem dưỡng da", "Son môi", "Sữa rửa mặt", "Nước hoa mini",
                "Mặt nạ dưỡng ẩm", "Kem chống nắng"],
    "Sách & Văn phòng phẩm": ["Sổ tay ghi chú", "Bút bi cao cấp", "Sách kỹ năng sống",
                              "Giấy note", "Bìa hồ sơ", "Bộ bút màu"],
    "Đồ chơi trẻ em": ["Xếp hình Lego", "Búp bê", "Xe điều khiển từ xa",
                        "Bộ đồ chơi nấu ăn", "Gấu bông", "Đồ chơi lắp ráp"],
}


def generate_products(cur, category_ids):
    product_ids = []
    for cat_id, cat_name in zip(category_ids, CATEGORIES):
        templates = PRODUCT_NAME_TEMPLATES[cat_name]
        for _ in range(NUM_PRODUCTS_PER_CATEGORY):
            base_name = random.choice(templates)
            variant = random.choice(["", " Pro", " Mini", " Plus", " 2024", " Cao cấp"])
            product_name = f"{base_name}{variant}".strip()
            price = round(random.uniform(30000, 2000000), -3)  # làm tròn nghìn đồng
            cur.execute(
                """INSERT INTO products (category_id, product_name, unit_price)
                   VALUES (%s, %s, %s) RETURNING product_id""",
                (cat_id, product_name, price),
            )
            product_ids.append(cur.fetchone()[0])
    return product_ids


def generate_inventory(cur, product_ids):
    for pid in product_ids:
        stock = random.randint(0, 500)
        last_restocked = fake.date_time_between(start_date="-60d", end_date="now")
        cur.execute(
            """INSERT INTO inventory (product_id, stock_quantity, last_restocked)
               VALUES (%s, %s, %s)""",
            (pid, stock, last_restocked),
        )


def get_product_prices(cur, product_ids):
    cur.execute(
        "SELECT product_id, unit_price FROM products WHERE product_id = ANY(%s)",
        (product_ids,),
    )
    return dict(cur.fetchall())


def generate_orders_and_items(cur, customer_ids, product_ids):
    price_map = get_product_prices(cur, product_ids)

    for _ in range(NUM_ORDERS):
        customer_id = random.choice(customer_ids)
        order_date = random_date_weighted(START_DATE, END_DATE)
        status = random.choice(ORDER_STATUSES)

        cur.execute(
            """INSERT INTO orders (customer_id, order_date, status)
               VALUES (%s, %s, %s) RETURNING order_id""",
            (customer_id, order_date.date(), status),
        )
        order_id = cur.fetchone()[0]

        num_items = random.randint(1, MAX_ITEMS_PER_ORDER)
        chosen_products = random.sample(product_ids, min(num_items, len(product_ids)))

        for pid in chosen_products:
            quantity = random.randint(1, 4)
            unit_price = price_map[pid]
            cur.execute(
                """INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                   VALUES (%s, %s, %s, %s)""",
                (order_id, pid, quantity, unit_price),
            )


def main():
    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Đang sinh categories...")
        category_ids = generate_categories(cur)

        print("Đang sinh customers...")
        customer_ids = generate_customers(cur, NUM_CUSTOMERS)

        print("Đang sinh products...")
        product_ids = generate_products(cur, category_ids)

        print("Đang sinh inventory...")
        generate_inventory(cur, product_ids)

        print("Đang sinh orders + order_items (có thể mất chút thời gian)...")
        generate_orders_and_items(cur, customer_ids, product_ids)

        conn.commit()
        print("✅ Hoàn tất! Dữ liệu synthetic đã được nạp vào database bi_agent_demo.")

        # In nhanh vài số liệu để kiểm tra
        cur.execute("SELECT COUNT(*) FROM customers")
        print("Số khách hàng:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM products")
        print("Số sản phẩm:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM orders")
        print("Số đơn hàng:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM order_items")
        print("Số dòng order_items:", cur.fetchone()[0])

    except Exception as e:
        conn.rollback()
        print("❌ Có lỗi xảy ra, đã rollback:", e)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
