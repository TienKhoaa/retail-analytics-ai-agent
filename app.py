"""
Giao diện chat Streamlit cho Retail Analytics Agent.

Yêu cầu:
    - File này phải nằm CÙNG THƯ MỤC với agent.py
    - pip install streamlit pandas

Cách chạy:
    streamlit run app.py
"""

import re

import pandas as pd
import streamlit as st

from agent import ask

# Ép khối hiển thị code (câu SQL) tự động xuống dòng thay vì tràn ngang phải kéo thanh cuộn
st.markdown(
    """
    <style>
    pre, code {
        white-space: pre-wrap !important;
        word-break: break-word !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Các từ khóa SQL sẽ được xuống dòng riêng để câu lệnh dễ đọc hơn
SQL_KEYWORDS_NEWLINE = [
    "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT",
    "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "FULL JOIN",
    "UNION", "UNION ALL",
]


def format_sql_for_display(sql: str) -> str:
    """
    Chèn xuống dòng trước các từ khóa chính (FROM, WHERE, JOIN, GROUP BY...)
    để câu SQL hiển thị dễ đọc trên giao diện, không bị dồn thành 1 dòng dài.
    """
    formatted = sql.strip()
    # Sắp xếp từ dài đến ngắn để tránh "JOIN" bị cắt trước khi khớp "LEFT JOIN"
    for keyword in sorted(SQL_KEYWORDS_NEWLINE, key=len, reverse=True):
        pattern = r"(?<!\n)\b" + re.escape(keyword) + r"\b"
        formatted = re.sub(pattern, f"\n{keyword}", formatted, flags=re.IGNORECASE)
    return formatted.strip()


def try_auto_chart(df: pd.DataFrame):
    """
    Tự động vẽ biểu đồ nếu dữ liệu phù hợp: có ít nhất 1 cột số và 1 cột
    dạng danh mục/thời gian, và không quá nhiều dòng (tránh chart rối mắt).
    Trả về True nếu đã vẽ được chart, False nếu không phù hợp.
    """
    if df is None or df.empty or len(df) > 50 or len(df.columns) < 2:
        return False

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

    if not numeric_cols or not non_numeric_cols:
        return False

    label_col = non_numeric_cols[0]
    value_col = numeric_cols[0]

    try:
        chart_df = df.set_index(label_col)[[value_col]]
        st.bar_chart(chart_df)
        return True
    except Exception:
        return False

st.set_page_config(
    page_title="Retail Analytics Agent",
    page_icon="📊",
    layout="centered",
)

st.title("📊 Retail Analytics Agent")
st.caption(
    "Hỏi bất kỳ câu hỏi nào về dữ liệu bán lẻ (đơn hàng, khách hàng, sản phẩm, tồn kho) "
    "bằng ngôn ngữ tự nhiên — Agent sẽ tự sinh SQL và trả lời."
)

# Vài câu hỏi gợi ý để người xem demo biết nên hỏi gì
with st.expander("💡 Gợi ý câu hỏi mẫu"):
    st.markdown(
        """
        - Doanh thu theo từng danh mục sản phẩm là bao nhiêu?
        - Top 5 sản phẩm bán chạy nhất?
        - Khách hàng nào có nhiều đơn hàng nhất năm 2025?
        - Sản phẩm nào tồn kho dưới 50?
        - Tỷ lệ đơn hàng bị hủy là bao nhiêu phần trăm?
        """
    )

# Khởi tạo lịch sử hội thoại trong session
if "messages" not in st.session_state:
    st.session_state.messages = []

# Hiển thị lại lịch sử hội thoại mỗi lần Streamlit rerun
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sql"):
            with st.expander("Xem câu SQL đã sinh"):
                st.code(format_sql_for_display(msg["sql"]), language="sql")
        if msg.get("dataframe") is not None:
            st.dataframe(msg["dataframe"], use_container_width=True)
            try_auto_chart(msg["dataframe"])

# Ô nhập câu hỏi
question = st.chat_input("Nhập câu hỏi của bạn...")

if question:
    # Hiển thị câu hỏi của người dùng ngay lập tức
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Gọi Agent xử lý, truyền kèm lịch sử hội thoại (không tính lượt hiện tại)
    conversation_history = [
        {"question": m["content"], "answer": st.session_state.messages[i + 1]["content"]}
        for i, m in enumerate(st.session_state.messages[:-1])
        if m["role"] == "user" and i + 1 < len(st.session_state.messages)
        and st.session_state.messages[i + 1]["role"] == "assistant"
    ]

    with st.chat_message("assistant"):
        with st.spinner("Đang phân tích và truy vấn dữ liệu..."):
            result = ask(question, history=conversation_history)

        if result["error"]:
            st.error(f"❌ {result['error']}")
            st.code(format_sql_for_display(result["sql"]), language="sql")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"❌ {result['error']}", "sql": result["sql"]}
            )
        else:
            st.markdown(result["answer"])

            with st.expander("Xem câu SQL đã sinh"):
                st.code(format_sql_for_display(result["sql"]), language="sql")

            df = None
            if result["rows"]:
                df = pd.DataFrame(result["rows"], columns=result["columns"])
                st.dataframe(df, use_container_width=True)
                try_auto_chart(df)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": result["answer"],
                    "sql": result["sql"],
                    "dataframe": df,
                }
            )

# Nút xóa lịch sử hội thoại
if st.session_state.messages:
    if st.button("🗑️ Xóa lịch sử hội thoại"):
        st.session_state.messages = []
        st.rerun()
