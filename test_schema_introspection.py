"""
Unit test cho schema_introspection.py — kiểm tra logic ghép mô tả schema
KHÔNG cần kết nối database thật (dùng dữ liệu giả lập).

Cách chạy:
    pytest test_schema_introspection.py -v
"""

from schema_introspection import build_schema_description


class TestBuildSchemaDescription:
    def test_includes_all_table_names(self):
        tables = {
            "customers": [("customer_id", "integer"), ("customer_name", "character varying")],
            "orders": [("order_id", "integer"), ("customer_id", "integer")],
        }
        description = build_schema_description(tables, foreign_keys=[])
        assert "customers" in description
        assert "orders" in description

    def test_includes_all_column_names(self):
        tables = {"customers": [("customer_id", "integer"), ("city", "character varying")]}
        description = build_schema_description(tables, foreign_keys=[])
        assert "customer_id" in description
        assert "city" in description

    def test_includes_foreign_keys(self):
        tables = {"orders": [("order_id", "integer"), ("customer_id", "integer")]}
        fks = [("orders", "customer_id", "customers", "customer_id")]
        description = build_schema_description(tables, foreign_keys=fks)
        assert "orders.customer_id -> customers.customer_id" in description

    def test_no_foreign_keys_does_not_crash(self):
        tables = {"customers": [("customer_id", "integer")]}
        description = build_schema_description(tables, foreign_keys=[])
        assert "customers" in description  # vẫn chạy bình thường, không lỗi

    def test_business_notes_are_included(self):
        tables = {"orders": [("status", "character varying")]}
        notes = {"orders.status": "có giá trị: 'completed', 'pending'"}
        description = build_schema_description(tables, foreign_keys=[], business_notes=notes)
        assert "có giá trị: 'completed', 'pending'" in description

    def test_works_with_arbitrary_table_names(self):
        """
        Kiểm tra tính tổng quát: schema với tên bảng hoàn toàn khác (không phải
        customers/orders quen thuộc) vẫn được mô tả đúng — mô phỏng trường hợp
        đổi sang database của 1 công ty khác.
        """
        tables = {
            "hoa_don": [("ma_hoa_don", "integer"), ("ngay_lap", "date")],
            "khach_hang": [("ma_khach_hang", "integer"), ("ten", "character varying")],
        }
        description = build_schema_description(tables, foreign_keys=[])
        assert "hoa_don" in description
        assert "khach_hang" in description
        assert "ma_hoa_don" in description
