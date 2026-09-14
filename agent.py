"""
Text-to-SQL Analytics Agent
----------------------------
Nhận câu hỏi bằng ngôn ngữ tự nhiên (tiếng Việt/Anh), tự sinh câu lệnh SQL,
chạy trên Postgres, và trả lời lại bằng ngôn ngữ tự nhiên kèm dữ liệu.

Yêu cầu trước khi chạy:
    pip install google-generativeai psycopg2-binary python-dotenv
    Đã tạo file .env chứa GOOGLE_API_KEY=your_key_here

Cách chạy (demo dòng lệnh, chưa cần giao diện):
    python agent.py
"""

import os
import re
import time

import psycopg2
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

from schema_introspection import get_schema_description

# ============================================================
# CẤU HÌNH
# ============================================================
load_dotenv()  # đọc file .env

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("Chưa tìm thấy GOOGLE_API_KEY trong file .env")

client = genai.Client(api_key=GOOGLE_API_KEY)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "bi_agent_demo"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}
if not DB_CONFIG["password"]:
    raise ValueError("Chưa tìm thấy DB_PASSWORD trong file .env")

MODEL_NAME = "gemini-3.6-flash"  # model miễn phí, nhẹ, ít bị quá tải hơn bản mới nhất
# Nếu model này báo lỗi "not found", chạy thử:
#   for m in client.models.list(): print(m.name)
# rồi thay MODEL_NAME bằng 1 tên model có hỗ trợ generateContent trong danh sách đó.

# ============================================================
# MÔ TẢ SCHEMA — Agent cần biết cấu trúc database để sinh SQL đúng
# ------------------------------------------------------------
# Thay vì viết tay cố định, schema được TỰ ĐỘNG đọc từ chính database
# đang kết nối (xem schema_introspection.py). Nhờ vậy, đổi DB_CONFIG sang
# database của công ty khác thì Agent tự thích nghi, không cần sửa code.
# Ghi chú nghiệp vụ bổ sung (ý nghĩa cột status, cách tính doanh thu...)
# được khai báo trong BUSINESS_NOTES của schema_introspection.py.
# ============================================================
SCHEMA_DESCRIPTION = get_schema_description(DB_CONFIG)

SQL_GENERATION_PROMPT = """{schema}

{history_section}
Nhiệm vụ của bạn: chuyển câu hỏi sau đây thành ĐÚNG MỘT câu lệnh SQL PostgreSQL hợp lệ.
Nếu câu hỏi hiện tại tham chiếu đến ngữ cảnh của các câu hỏi trước (ví dụ: "còn tháng trước thì sao?",
"vậy còn sản phẩm B?"), hãy dùng lịch sử hội thoại ở trên để hiểu đúng ý người dùng.

QUY TẮC BẮT BUỘC:
- Chỉ được dùng câu lệnh SELECT. Tuyệt đối không dùng INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE.
- Chỉ trả về câu SQL thuần túy, KHÔNG kèm giải thích, KHÔNG dùng markdown code block (không có ```sql).
- Tuân theo đúng các ghi chú nghiệp vụ (nếu có) được nêu kèm theo từng bảng/cột ở phần schema phía trên.
- Nếu câu hỏi không thể trả lời được bằng dữ liệu hiện có, trả về: SELECT 'Không thể trả lời câu hỏi này với dữ liệu hiện có' AS message;

Câu hỏi hiện tại: {question}

SQL:"""

ANSWER_GENERATION_PROMPT = """Câu hỏi của người dùng: {question}

Kết quả truy vấn từ database (dạng bảng):
{result}

Hãy trả lời câu hỏi trên bằng ngôn ngữ tự nhiên, ngắn gọn, dễ hiểu, dựa hoàn toàn vào
kết quả trên. Nếu kết quả rỗng, hãy nói rõ là không tìm thấy dữ liệu phù hợp.
Không bịa thêm thông tin ngoài kết quả được cung cấp."""


# ============================================================
# HÀM XỬ LÝ
# ============================================================
# ============================================================
# HÀM GỌI API CÓ TỰ ĐỘNG THỬ LẠI (khi server Google quá tải)
# ============================================================
def call_gemini_with_retry(prompt: str, max_retries: int = 3, wait_seconds: int = 5) -> str:
    """Gọi Gemini, tự động thử lại nếu gặp lỗi 503 (quá tải) hoặc 429 (rate limit)."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            return response.text.strip()
        except genai_errors.ServerError as e:
            last_error = e
            print(f"⚠️  Server Google đang quá tải (lần thử {attempt}/{max_retries}), "
                  f"chờ {wait_seconds}s rồi thử lại...")
            time.sleep(wait_seconds)
        except genai_errors.ClientError as e:
            # Lỗi 429 (rate limit) cũng đáng để thử lại; các lỗi client khác thì raise luôn
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                last_error = e
                print(f"⚠️  Đạt giới hạn rate limit (lần thử {attempt}/{max_retries}), "
                      f"chờ {wait_seconds}s rồi thử lại...")
                time.sleep(wait_seconds)
            else:
                raise
    raise last_error


def format_history(history: list[dict] | None) -> str:
    """
    Định dạng lịch sử hội thoại (danh sách các câu hỏi + câu trả lời trước đó)
    thành đoạn text đưa vào prompt. history là list các dict {"question": ..., "answer": ...}.
    Chỉ lấy 3 lượt gần nhất để tránh prompt quá dài.
    """
    if not history:
        return ""

    recent = history[-3:]
    lines = ["Lịch sử hội thoại gần đây:"]
    for turn in recent:
        lines.append(f"- Người dùng hỏi: {turn['question']}")
        lines.append(f"  Trả lời trước đó: {turn['answer']}")
    return "\n".join(lines) + "\n"


def generate_sql(question: str, history: list[dict] | None = None) -> str:
    """Gọi Gemini để sinh câu lệnh SQL từ câu hỏi tự nhiên, có xét lịch sử hội thoại."""
    prompt = SQL_GENERATION_PROMPT.format(
        schema=SCHEMA_DESCRIPTION,
        history_section=format_history(history),
        question=question,
    )
    sql = call_gemini_with_retry(prompt)

    # Dọn dẹp nếu Gemini lỡ trả về kèm markdown code block
    sql = re.sub(r"^```sql\s*|\s*```$", "", sql, flags=re.MULTILINE).strip()
    return sql


def is_safe_select(sql: str) -> bool:
    """
    Kiểm tra an toàn: chỉ cho phép câu lệnh bắt đầu bằng SELECT,
    và không chứa các từ khóa nguy hiểm.
    """
    normalized = sql.strip().lower()
    if not normalized.startswith("select"):
        return False

    forbidden_keywords = [
        "insert", "update", "delete", "drop", "alter",
        "truncate", "create", "grant", "revoke", ";--", "/*",
    ]
    # Cho phép 1 dấu ; ở cuối câu, nhưng chặn nếu có nhiều câu lệnh nối nhau
    if normalized.count(";") > 1:
        return False

    return not any(keyword in normalized for keyword in forbidden_keywords)


DEFAULT_ROW_LIMIT = 100


def enforce_row_limit(sql: str, max_rows: int = DEFAULT_ROW_LIMIT) -> str:
    """
    Nếu câu SQL chưa có mệnh đề LIMIT, tự động thêm vào để tránh Agent
    trả về quá nhiều dòng (tốn thời gian, tốn token khi diễn giải kết quả).
    Nếu người dùng/Agent đã tự đặt LIMIT nhỏ hơn max_rows thì giữ nguyên.
    """
    sql_clean = sql.strip().rstrip(";")
    match = re.search(r"\blimit\s+(\d+)\b", sql_clean, flags=re.IGNORECASE)

    if match:
        existing_limit = int(match.group(1))
        if existing_limit > max_rows:
            # Thay giới hạn quá lớn bằng giới hạn an toàn
            sql_clean = re.sub(
                r"\blimit\s+\d+\b", f"LIMIT {max_rows}", sql_clean, flags=re.IGNORECASE
            )
        return sql_clean + ";"

    return f"{sql_clean} LIMIT {max_rows};"


QUERY_TIMEOUT_MS = 5000  # tối đa 5 giây cho mỗi truy vấn, tránh query nặng làm treo app


def run_sql(sql: str):
    """Chạy câu SQL trên Postgres, trả về (column_names, rows). Có giới hạn thời gian chạy."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute(f"SET statement_timeout = {QUERY_TIMEOUT_MS};")
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        return columns, rows
    finally:
        conn.close()


def format_result(columns, rows, max_rows=20) -> str:
    """Định dạng kết quả truy vấn thành dạng bảng text đơn giản để đưa vào prompt."""
    if not rows:
        return "(Không có dữ liệu)"

    lines = [" | ".join(columns)]
    for row in rows[:max_rows]:
        lines.append(" | ".join(str(v) for v in row))

    if len(rows) > max_rows:
        lines.append(f"... và {len(rows) - max_rows} dòng khác")

    return "\n".join(lines)


def generate_natural_answer(question: str, result_text: str) -> str:
    """Gọi Gemini để diễn giải kết quả SQL thành câu trả lời tự nhiên."""
    prompt = ANSWER_GENERATION_PROMPT.format(question=question, result=result_text)
    return call_gemini_with_retry(prompt)


def ask(question: str, history: list[dict] | None = None) -> dict:
    """
    Hàm chính: nhận câu hỏi (và tùy chọn lịch sử hội thoại trước đó),
    trả về dict gồm sql đã sinh, kết quả thô, và câu trả lời tự nhiên.

    history: list các dict {"question": str, "answer": str} theo thứ tự thời gian,
             dùng để Agent hiểu ngữ cảnh khi người dùng hỏi tiếp ("còn tháng trước thì sao?").
    """
    sql = generate_sql(question, history=history)

    if not is_safe_select(sql):
        return {
            "question": question,
            "sql": sql,
            "error": "Câu SQL sinh ra không an toàn hoặc không phải câu SELECT hợp lệ.",
            "answer": None,
        }

    sql = enforce_row_limit(sql)

    try:
        columns, rows = run_sql(sql)
    except psycopg2.errors.QueryCanceled:
        return {
            "question": question,
            "sql": sql,
            "error": "Truy vấn mất quá nhiều thời gian để chạy (quá 5 giây) và đã bị hủy. "
                     "Thử đặt câu hỏi cụ thể hơn (VD: giới hạn theo khoảng thời gian).",
            "answer": None,
        }
    except psycopg2.errors.SyntaxError as e:
        return {
            "question": question,
            "sql": sql,
            "error": f"SQL do Agent sinh ra bị lỗi cú pháp: {e}. "
                     f"Thử diễn đạt lại câu hỏi theo cách khác.",
            "answer": None,
        }
    except psycopg2.errors.UndefinedColumn as e:
        return {
            "question": question,
            "sql": sql,
            "error": f"Agent tham chiếu nhầm tên cột không tồn tại: {e}. "
                     f"Thử diễn đạt lại câu hỏi theo cách khác.",
            "answer": None,
        }
    except Exception as e:
        return {
            "question": question,
            "sql": sql,
            "error": f"Lỗi khi chạy SQL: {e}",
            "answer": None,
        }

    result_text = format_result(columns, rows)
    answer = generate_natural_answer(question, result_text)

    return {
        "question": question,
        "sql": sql,
        "error": None,
        "columns": columns,
        "rows": rows,
        "answer": answer,
    }


# ============================================================
# DEMO DÒNG LỆNH
# ============================================================
def main():
    print("=== Retail Analytics Agent (gõ 'exit' để thoát) ===\n")
    history: list[dict] = []

    while True:
        question = input("Câu hỏi của bạn: ").strip()
        if question.lower() in ("exit", "quit", "thoát"):
            break
        if not question:
            continue

        result = ask(question, history=history)

        print(f"\n[SQL được sinh ra]\n{result['sql']}\n")

        if result["error"]:
            print(f"❌ {result['error']}\n")
            continue

        print(f"[Trả lời]\n{result['answer']}\n")
        print("-" * 60)

        history.append({"question": question, "answer": result["answer"]})


if __name__ == "__main__":
    main()
