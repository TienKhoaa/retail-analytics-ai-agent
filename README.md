# 📊 Retail Analytics AI Agent

Một AI Agent cho phép người dùng đặt câu hỏi về dữ liệu kinh doanh bằng **ngôn ngữ tự nhiên** (tiếng Việt/tiếng Anh), tự động sinh câu lệnh SQL, truy vấn database, và trả lời kèm insight — không cần biết viết SQL.

> 💡 Đây là dự án cá nhân xây dựng để thực hành kết hợp kỹ năng **Data Analytics** và **AI Engineering**. Dữ liệu sử dụng là dữ liệu **synthetic (tự sinh)**, không phải dữ liệu thật của bất kỳ tổ chức nào.

---

## Tính năng chính

- **Text-to-SQL**: Chuyển câu hỏi ngôn ngữ tự nhiên thành câu lệnh SQL PostgreSQL chính xác
- **Trả lời tự nhiên**: Diễn giải kết quả truy vấn thành câu trả lời dễ hiểu, không chỉ trả về bảng số liệu thô
- **Schema Introspection**: Agent tự động đọc cấu trúc database (bảng, cột, khóa ngoại) qua `information_schema`, không hard-code — có thể tái sử dụng cho bất kỳ database Postgres nào, không riêng gì bộ dữ liệu bán lẻ trong demo này
- **Guardrail bảo mật**: Chỉ cho phép thực thi câu lệnh `SELECT`, chặn tuyệt đối `INSERT`/`UPDATE`/`DELETE`/`DROP`...
- **Giới hạn & timeout truy vấn**: Tự động giới hạn số dòng trả về và thời gian chạy tối đa, tránh treo hệ thống
- **Ghi nhớ ngữ cảnh hội thoại**: Hỏi tiếp được kiểu "còn tháng trước thì sao?" mà không cần lặp lại toàn bộ câu hỏi
- **Giao diện chat trực quan**: Xây bằng Streamlit, có hiển thị SQL đã sinh, bảng kết quả, và biểu đồ tự động
- **Unit test**: Kiểm thử các hàm quan trọng (đặc biệt là lớp bảo mật `is_safe_select`)

---

## Kiến trúc

```
Câu hỏi (tiếng Việt/Anh)
        │
        ▼
┌───────────────────┐      ┌──────────────────────────┐
│  Schema            │◄────►│  information_schema       │
│  Introspection     │      │  (đọc cấu trúc DB tự động)│
└─────────┬──────────┘      └──────────────────────────┘
          │ (mô tả schema)
          ▼
┌───────────────────┐
│   Gemini API        │  →  sinh câu lệnh SQL
└─────────┬──────────┘
          │
          ▼
┌───────────────────┐
│  Guardrail bảo mật  │  →  chỉ cho phép SELECT
│  (is_safe_select)   │
└─────────┬──────────┘
          │
          ▼
┌───────────────────┐
│   PostgreSQL        │  →  thực thi truy vấn (có timeout, LIMIT)
└─────────┬──────────┘
          │ (kết quả thô)
          ▼
┌───────────────────┐
│   Gemini API        │  →  diễn giải thành câu trả lời tự nhiên
└─────────┬──────────┘
          │
          ▼
   Giao diện Streamlit (chat + bảng + biểu đồ)
```

---

## Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.12 |
| Database | PostgreSQL |
| AI Model | Google Gemini API |
| Giao diện | Streamlit |
| Sinh dữ liệu mẫu | Faker, NumPy |
| Kết nối DB | psycopg2 |
| Testing | pytest |

---

## Cấu trúc project

```
├── agent.py                    # Logic chính của Agent (Text-to-SQL, guardrail, retry)
├── schema_introspection.py     # Module tự động đọc cấu trúc database
├── app.py                      # Giao diện chat Streamlit
├── create_schema.sql           # Script tạo schema database mẫu (bán lẻ)
├── generate_data.py            # Script sinh dữ liệu synthetic
├── test_agent.py                # Unit test cho agent.py
├── test_schema_introspection.py # Unit test cho schema_introspection.py
├── requirements.txt
└── .env.example                 # Mẫu file cấu hình biến môi trường
```

---

## Cài đặt & chạy thử

### 1. Clone project và cài đặt môi trường

```bash
git clone <link-repo-cua-ban>
cd retail-analytics-agent
python -m venv venv
venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường

Copy `.env.example` thành `.env` và điền API key thật:

```
GOOGLE_API_KEY=your_gemini_api_key_here
```

> Lấy API key miễn phí tại [Google AI Studio](https://aistudio.google.com)

### 3. Tạo database & sinh dữ liệu mẫu

```bash
psql -h localhost -U postgres -d bi_agent_demo -f create_schema.sql
python generate_data.py
```

### 4. Chạy Agent

**Bản dòng lệnh (CLI):**
```bash
python agent.py
```

**Giao diện chat (khuyến nghị):**
```bash
streamlit run app.py
```

---

## Ví dụ câu hỏi

- "Doanh thu theo từng danh mục sản phẩm là bao nhiêu?"
- "Top 5 sản phẩm bán chạy nhất?"
- "Khách hàng nào có nhiều đơn hàng nhất năm 2025?"
- "Sản phẩm nào tồn kho dưới 50?"
- "Tỷ lệ đơn hàng bị hủy là bao nhiêu phần trăm?"

---

## Về bảo mật

- Agent **chỉ được phép** thực thi câu lệnh `SELECT` — mọi câu lệnh khác (kể cả khi bị AI sinh nhầm) đều bị chặn ở tầng `is_safe_select()` trước khi chạy trên database thật.
- Mỗi truy vấn có **timeout 5 giây** và **giới hạn tối đa 100 dòng** kết quả để tránh ảnh hưởng hiệu năng hệ thống.
- API key và thông tin kết nối database được lưu trong file `.env`, không commit lên Git (`.gitignore` đã cấu hình sẵn).

---

## Chạy test

```bash
pip install pytest
pytest -v
```

---

## Giới hạn hiện tại

- `is_safe_select()` kiểm tra bằng cách tìm từ khóa cấm dạng substring — có thể chặn nhầm nếu tên cột chứa từ khóa đó (ví dụ cột `updated_at`). Giới hạn này đã được ghi nhận lại trong test case.
- Schema Introspection đọc được **cấu trúc kỹ thuật** (tên bảng/cột, khóa ngoại) nhưng không tự hiểu **ý nghĩa nghiệp vụ** — cần bổ sung thủ công qua `BUSINESS_NOTES` trong `schema_introspection.py`.
- Dữ liệu trong demo là dữ liệu synthetic, không phản ánh dữ liệu thật của bất kỳ doanh nghiệp cụ thể nào.

---

## Hướng phát triển tiếp theo

- Xây lớp ETL/Ingestion riêng để nạp dữ liệu từ nhiều nguồn khác nhau (Excel, API, CDC từ Kafka) vào database chuẩn hóa mà Agent sử dụng
- Chuyển `BUSINESS_NOTES` từ hard-code sang file cấu hình YAML/JSON riêng theo từng khách hàng/database
- Thêm cơ chế đánh giá độ chính xác của SQL sinh ra (evaluation set)
- Deploy dạng đa người dùng với xác thực (authentication) và phân quyền dữ liệu

---

## License

Dự án cá nhân phục vụ mục đích học tập và portfolio.
