"""
Unit test cho các hàm quan trọng của Agent, đặc biệt là lớp bảo mật is_safe_select().

Cách chạy:
    pip install pytest
    pytest test_agent.py -v
"""

from agent import enforce_row_limit, is_safe_select


class TestIsSafeSelect:
    """Kiểm tra hàm is_safe_select() — lớp bảo vệ ngăn Agent chạy lệnh SQL nguy hiểm."""

    def test_valid_select_is_allowed(self):
        assert is_safe_select("SELECT * FROM orders;") is True

    def test_valid_select_case_insensitive(self):
        assert is_safe_select("select customer_name from customers") is True

    def test_select_with_join_is_allowed(self):
        sql = """SELECT c.customer_name, COUNT(o.order_id)
                 FROM customers c JOIN orders o ON c.customer_id = o.customer_id
                 GROUP BY c.customer_name;"""
        assert is_safe_select(sql) is True

    def test_insert_is_blocked(self):
        assert is_safe_select("INSERT INTO orders VALUES (1, 2, 3);") is False

    def test_update_is_blocked(self):
        assert is_safe_select("UPDATE products SET unit_price = 0;") is False

    def test_delete_is_blocked(self):
        assert is_safe_select("DELETE FROM orders;") is False

    def test_drop_table_is_blocked(self):
        assert is_safe_select("DROP TABLE customers;") is False

    def test_drop_disguised_after_select_is_blocked(self):
        """Câu lệnh nối chuỗi kiểu SELECT ... ; DROP TABLE ... phải bị chặn."""
        sql = "SELECT * FROM customers; DROP TABLE customers;"
        assert is_safe_select(sql) is False

    def test_truncate_is_blocked(self):
        assert is_safe_select("TRUNCATE TABLE orders;") is False

    def test_non_select_statement_is_blocked(self):
        assert is_safe_select("EXPLAIN SELECT * FROM orders;") is False

    def test_empty_string_is_blocked(self):
        assert is_safe_select("") is False

    def test_select_containing_forbidden_word_as_substring_in_identifier(self):
        """
        Lưu ý: đây là 1 giới hạn đã biết của cách kiểm tra bằng substring — nếu tên cột/bảng
        vô tình chứa từ khóa cấm (vd: 'updated_at'), câu lệnh sẽ bị chặn nhầm.
        Test này ghi nhận hành vi hiện tại để không quên giới hạn này khi nâng cấp sau.
        """
        sql = "SELECT updated_at FROM orders;"
        assert is_safe_select(sql) is False  # false positive đã biết


class TestEnforceRowLimit:
    """Kiểm tra hàm enforce_row_limit() — tự động giới hạn số dòng trả về."""

    def test_adds_limit_when_missing(self):
        sql = "SELECT * FROM orders"
        result = enforce_row_limit(sql, max_rows=100)
        assert "LIMIT 100" in result

    def test_keeps_smaller_existing_limit(self):
        sql = "SELECT * FROM orders LIMIT 10"
        result = enforce_row_limit(sql, max_rows=100)
        assert "LIMIT 10" in result
        assert "LIMIT 100" not in result

    def test_caps_larger_existing_limit(self):
        sql = "SELECT * FROM orders LIMIT 5000"
        result = enforce_row_limit(sql, max_rows=100)
        assert "LIMIT 100" in result
        assert "LIMIT 5000" not in result

    def test_result_ends_with_semicolon(self):
        sql = "SELECT * FROM orders"
        result = enforce_row_limit(sql, max_rows=100)
        assert result.strip().endswith(";")
