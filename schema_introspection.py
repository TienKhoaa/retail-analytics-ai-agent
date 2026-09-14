"""
Schema Introspection
---------------------
Module này giúp Agent tự động "khám phá" cấu trúc của bất kỳ database Postgres nào
đang kết nối (tên bảng, tên cột, kiểu dữ liệu, khóa ngoại), thay vì phải viết tay
mô tả schema cố định trong code.

Nhờ vậy, Agent có thể tái sử dụng cho database của công ty khác mà không cần sửa code —
chỉ cần đổi thông tin kết nối (DB_CONFIG) và (tùy chọn) bổ sung ghi chú nghiệp vụ riêng.
"""

import psycopg2

# ============================================================
# GHI CHÚ NGHIỆP VỤ BỔ SUNG (tùy chọn)
# ------------------------------------------------------------
# Introspection chỉ lấy được cấu trúc KỸ THUẬT (tên bảng/cột/kiểu dữ liệu),
# không tự hiểu được Ý NGHĨA NGHIỆP VỤ (vd: cột status có giá trị gì, đơn vị tiền tệ...).
# Với mỗi database/công ty khác nhau, có thể tùy chỉnh dict này để bổ sung ngữ cảnh,
# giúp Agent sinh SQL chính xác hơn. Để trống ("") nếu không có ghi chú gì thêm.
# ============================================================
BUSINESS_NOTES = {
    "products.unit_price": "giá hiện tại, đơn vị: VNĐ",
    "order_items.unit_price": "giá tại thời điểm đặt hàng (có thể khác giá hiện tại trong bảng products)",
    "order_items": "Doanh thu của 1 dòng = quantity * unit_price",
    "orders.status": "có giá trị: 'completed', 'pending', 'cancelled', 'returned'. "
                      "Khi hỏi đơn hàng 'thành công'/'hoàn tất', lọc theo status = 'completed'",
}


def fetch_tables_and_columns(conn, schema: str = "public") -> dict:
    """
    Trả về dict {table_name: [(column_name, data_type), ...]} cho mọi bảng
    trong schema chỉ định (mặc định 'public').
    """
    query = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position;
    """
    cur = conn.cursor()
    cur.execute(query, (schema,))
    rows = cur.fetchall()

    tables: dict = {}
    for table_name, column_name, data_type in rows:
        tables.setdefault(table_name, []).append((column_name, data_type))
    return tables


def fetch_foreign_keys(conn, schema: str = "public") -> list:
    """
    Trả về danh sách quan hệ khóa ngoại dạng:
    [(bang_con, cot_khoa_ngoai, bang_cha, cot_tham_chieu), ...]
    """
    query = """
        SELECT
            tc.table_name AS bang_con,
            kcu.column_name AS cot_khoa_ngoai,
            ccu.table_name AS bang_cha,
            ccu.column_name AS cot_tham_chieu
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = %s
        ORDER BY tc.table_name;
    """
    cur = conn.cursor()
    cur.execute(query, (schema,))
    return cur.fetchall()


def build_schema_description(
    tables: dict, foreign_keys: list, business_notes: dict | None = None
) -> str:
    """
    Ghép thông tin đã khám phá được (bảng, cột, khóa ngoại) cùng ghi chú nghiệp vụ
    (nếu có) thành 1 đoạn text mô tả schema, dùng để đưa vào prompt cho Agent.
    """
    business_notes = business_notes or {}
    lines = ["Bạn đang làm việc với database PostgreSQL có các bảng sau:\n"]

    for i, (table_name, columns) in enumerate(tables.items(), start=1):
        column_list = ", ".join(col for col, _ in columns)
        lines.append(f"{i}. {table_name} ({column_list})")

        # Ghi chú cấp bảng (nếu có)
        if table_name in business_notes:
            lines.append(f"   - {business_notes[table_name]}")

        # Ghi chú cấp cột (nếu có)
        for col, _ in columns:
            note_key = f"{table_name}.{col}"
            if note_key in business_notes:
                lines.append(f"   - {col}: {business_notes[note_key]}")

        lines.append("")  # dòng trống ngăn cách giữa các bảng

    if foreign_keys:
        lines.append("Quan hệ khóa ngoại:")
        for child_table, child_col, parent_table, parent_col in foreign_keys:
            lines.append(f"- {child_table}.{child_col} -> {parent_table}.{parent_col}")

    return "\n".join(lines)


_cached_schema_description: str | None = None


def get_schema_description(db_config: dict, use_cache: bool = True) -> str:
    """
    Hàm chính: kết nối database, tự động khám phá schema, và trả về đoạn mô tả
    sẵn sàng đưa vào prompt cho Agent.

    Kết quả được cache lại trong bộ nhớ (schema hiếm khi đổi giữa các lần hỏi),
    dùng refresh_schema_cache() nếu cần đọc lại sau khi database thay đổi cấu trúc.
    """
    global _cached_schema_description

    if use_cache and _cached_schema_description is not None:
        return _cached_schema_description

    conn = psycopg2.connect(**db_config)
    try:
        tables = fetch_tables_and_columns(conn)
        foreign_keys = fetch_foreign_keys(conn)
    finally:
        conn.close()

    description = build_schema_description(tables, foreign_keys, BUSINESS_NOTES)
    _cached_schema_description = description
    return description


def refresh_schema_cache(db_config: dict) -> str:
    """Buộc đọc lại schema từ database (bỏ qua cache), dùng khi cấu trúc DB vừa thay đổi."""
    global _cached_schema_description
    _cached_schema_description = None
    return get_schema_description(db_config, use_cache=False)
