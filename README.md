# IVPDS — Intelligent Voice Phishing Detection System

IVPDS là hệ thống hỗ trợ phát hiện nguy cơ **Voice Phishing** bằng cách phân tích nội dung cuộc gọi, nhận diện các dấu hiệu đáng ngờ và đưa ra mức đánh giá rủi ro.

Hệ thống không khẳng định một người chắc chắn là kẻ lừa đảo. Kết quả chỉ được sử dụng cho mục đích **đánh giá rủi ro và cảnh báo sớm**.

---

## 1. Kiến trúc tổng thể

Kiến trúc đề xuất:

> **Client–Server + Modular Monolith Backend + Separate AI Service**

```text
React Native Mobile (User)
           |
           | REST API
           v
    Spring Boot Backend
           |
   +-------+--------+
   |                |
PostgreSQL        MinIO
   |
   +------------------------> FastAPI AI Service
                                  |
                           +------+------+
                           |             |
                        Whisper       NLP / Rules
                           |             |
                           +------> Risk Engine

React Admin Web
       |
       +--------------------> Spring Boot Backend
```

### Lý do chọn kiến trúc này

- Phù hợp với team 5 người và thời gian phát triển 3 Sprint.
- Backend vẫn là một ứng dụng chính nên dễ phát triển, test và debug.
- Các module nghiệp vụ được tách rõ trong Spring Boot.
- AI được tách riêng vì sử dụng Python và có vòng đời phát triển khác backend.
- Dễ chuyển lên AWS sau này mà không phải viết lại toàn bộ hệ thống.

---

## 2. Công nghệ sử dụng

| Thành phần | Công nghệ | Lý do lựa chọn |
|---|---|---|
| Mobile App | **React Native + TypeScript + Expo** | Một codebase cho Android/iOS; dùng chung kiến thức React/TypeScript với web; phát triển nhanh |
| Mobile State | **Zustand + TanStack Query** | Zustand quản lý local state đơn giản; TanStack Query quản lý dữ liệu từ API, cache và loading/error |
| Mobile API | **Axios** | Dễ tích hợp REST API, interceptor JWT, timeout và xử lý lỗi |
| Admin Web | **React + TypeScript + Vite** | Phù hợp dashboard quản trị; hệ sinh thái mạnh; build nhanh |
| Admin UI | **Ant Design** | Có sẵn Table, Form, Modal, Filter, Pagination, phù hợp trang quản trị |
| Backend | **Java 21 + Spring Boot 3** | Xử lý business logic, REST API, validation, transaction và security ổn định |
| Authentication | **Spring Security + JWT + Refresh Token + BCrypt** | Phân quyền USER/ADMIN; không phụ thuộc cloud ở giai đoạn development |
| ORM | **Spring Data JPA + Hibernate** | Làm việc với PostgreSQL thuận tiện, hỗ trợ transaction và quan hệ dữ liệu |
| Database | **PostgreSQL** | Phù hợp dữ liệu quan hệ, truy vấn lịch sử, filter, report và statistics |
| DB Migration | **Flyway** | Đồng bộ version database schema giữa các thành viên |
| Object Storage | **MinIO** | Lưu file audio riêng khỏi database; tương thích S3 nên dễ migrate sang AWS |
| Audio Processing | **FFmpeg** | Chuẩn hóa codec, sample rate, mono và định dạng audio trước STT |
| Speech-to-Text | **Whisper** | Hỗ trợ tiếng Việt tốt, có thể chạy/test local |
| AI Service | **Python + FastAPI** | Python phù hợp AI/ML; FastAPI nhẹ, dễ tạo API cho Spring Boot gọi |
| NLP / ML | **Hugging Face Transformers + PyTorch + scikit-learn** | Phù hợp text classification, thử nghiệm model và đánh giá chất lượng |
| Detection | **Rule Engine + NLP Model** | Rule dễ giải thích; NLP xử lý ngữ cảnh khi không có keyword trực tiếp |
| Risk Engine | **Custom Python Risk Scoring** | Tổng hợp indicator, rule score và model probability thành Risk Score |
| API Docs | **OpenAPI + Swagger** | Giúp System Team và AI Team thống nhất API contract |
| Testing | **JUnit 5, Mockito, Testcontainers, pytest, Postman** | Kiểm thử backend, database, AI service và API integration |
| Dev Environment | **Docker + Docker Compose** | Đồng nhất môi trường chạy giữa các thành viên |
| Source Control | **Git + GitHub** | Branch, Pull Request, Code Review và quản lý source code |

---

## 3. Mobile App — User

### Công nghệ

```text
React Native
TypeScript
Expo
React Navigation
Zustand
TanStack Query
Axios
Expo SecureStore
Expo Audio
Expo Document Picker
Expo Image Picker
```

### Phạm vi chính

- Đăng ký / đăng nhập.
- Quản lý hồ sơ cá nhân.
- Đổi / quên mật khẩu.
- Ghi âm hoặc upload audio.
- Gửi yêu cầu phân tích cuộc gọi.
- Xem Risk Score và Risk Level.
- Xem transcript và các dấu hiệu nghi ngờ.
- Xem lịch sử phân tích.
- Tìm kiếm số điện thoại trong blacklist.
- Bật/tắt cảnh báo blacklist.

---

## 4. Admin Web

### Công nghệ

```text
React
TypeScript
Vite
React Router
TanStack Query
Axios
Ant Design
```

### Phạm vi chính

- Quản lý tài khoản người dùng.
- Theo dõi các analysis có mức rủi ro cao.
- Xem chi tiết kết quả phân tích.
- Quản lý phishing pattern.
- Quản lý blacklist.
- Xem báo cáo và thống kê.
- Dashboard quản trị.

---

## 5. Backend

### Công nghệ

```text
Java 21
Spring Boot 3
Spring Web
Spring Security
Spring Validation
Spring Data JPA
Hibernate
Flyway
```

### Kiến trúc Backend

Backend sử dụng **Modular Monolith**.

```text
backend/
├── auth/
├── user/
├── call/
├── audio/
├── analysis/
├── history/
├── blacklist/
├── notification/
├── admin/
└── phishingpattern/
```

Mỗi module có trách nhiệm riêng nhưng vẫn chạy trong cùng một Spring Boot application.

### Vai trò Backend

- Xử lý authentication và authorization.
- Quản lý user.
- Quản lý metadata audio.
- Tạo analysis request.
- Gọi AI Service.
- Lưu transcript và kết quả AI.
- Quản lý lịch sử.
- Quản lý blacklist.
- Cung cấp API cho mobile và admin web.

---

## 6. Database

### Công nghệ

**PostgreSQL**

Các bảng dự kiến:

```text
users
roles
user_roles
call_records
audio_files
transcripts
analyses
risk_results
risk_indicators
phishing_patterns
blacklist_numbers
notifications
```

Audio không nên lưu trực tiếp trong PostgreSQL. Database chỉ lưu metadata và đường dẫn/object key của file.

---

## 7. Audio Storage

### Công nghệ

**MinIO**

```text
React Native
      |
      v
Spring Boot
      |
      v
    MinIO
```

MinIO được dùng ở giai đoạn development vì:

- Chạy local dễ.
- Không làm database phình to vì file audio.
- API tương thích Amazon S3.
- Sau này chuyển `MinIO -> Amazon S3` tương đối ít thay đổi.

---

## 8. AI Pipeline

```text
Audio
  |
  v
FFmpeg
  |
  v
Whisper
  |
  v
Transcript
  |
  +-----------------------+
  |                       |
  v                       v
Rule Engine           NLP Model
  |                       |
  +-----------+-----------+
              |
              v
         Risk Engine
              |
              v
    LOW / MEDIUM / HIGH
```

### FFmpeg

Dùng để:

- Kiểm tra định dạng audio.
- Convert codec.
- Chuẩn hóa sample rate.
- Chuyển mono.
- Chuẩn bị audio trước Speech-to-Text.

### Whisper

Chuyển audio tiếng Việt thành transcript để AI tiếp tục phân tích.

### Rule Engine

Dùng cho các tín hiệu rõ ràng như:

```text
OTP_REQUEST
MONEY_TRANSFER
BANK_IMPERSONATION
URGENCY
ACCOUNT_LOCK_THREAT
SENSITIVE_INFORMATION
```

Rule Engine phù hợp với các pattern dễ xác định và có ưu điểm là dễ giải thích.

### NLP Model

Sử dụng:

```text
Hugging Face Transformers
PyTorch
scikit-learn
```

NLP giúp phát hiện ngữ nghĩa và scam intent ngay cả khi hội thoại không chứa keyword trực tiếp.

Có thể nghiên cứu các model phù hợp tiếng Việt như **PhoBERT**.

---

## 9. Risk Engine

Risk Engine tổng hợp nhiều tín hiệu:

```text
Rule Score
     +
Model Probability
     +
Indicator Severity
     |
     v
Final Risk Score
```

Ví dụ ban đầu:

```text
0 - 29    LOW
30 - 59   MEDIUM
60 - 100  HIGH
```

Các ngưỡng này cần được điều chỉnh sau khi AI Team đánh giá trên dataset thực tế.

---

## 10. API Contract

Các thành phần giao tiếp bằng **REST API + JSON**.

```text
React Native  ---> Spring Boot
React Web     ---> Spring Boot
Spring Boot   ---> FastAPI AI Service
```

AI Service nên trả về cấu trúc thống nhất, ví dụ:

```json
{
  "transcript": "...",
  "riskScore": 85,
  "riskLevel": "HIGH",
  "confidence": 0.91,
  "indicators": [
    "OTP_REQUEST",
    "BANK_IMPERSONATION"
  ]
}
```

OpenAPI/Swagger được dùng để System Team và AI Team thống nhất request/response ngay từ đầu.

---

## 11. Testing

### System Team

```text
JUnit 5
Mockito
Spring Boot Test
Testcontainers
Postman
```

### AI Team

```text
pytest
scikit-learn metrics
```

Các metric AI cần theo dõi:

```text
Precision
Recall
F1-score
Confusion Matrix
False Positive
False Negative
```

---

## 12. Development Environment

Các service local:

```text
Spring Boot Backend
FastAPI AI Service
PostgreSQL
MinIO
```

Tất cả chạy bằng:

```text
Docker
Docker Compose
```

Mục tiêu là mọi thành viên sử dụng cùng một môi trường development.

---

## 13. Source Code Management

Đề xuất chia repository:

```text
ivpds-mobile
ivpds-admin-web
ivpds-backend
ivpds-ai
```

Branch strategy:

```text
main
develop
feature/*
```

Workflow:

```text
Feature Branch
      |
      v
Pull Request
      |
      v
Code Review
      |
      v
develop
      |
      v
main
```

---

## 14. Phân chia Team

### System Team — 3 người

Phụ trách:

```text
React Native
React Admin Web
Spring Boot
PostgreSQL
MinIO
Authentication
Business Logic
Integration
Testing
```

### AI Team — 2 người

Phụ trách:

```text
FFmpeg
Whisper
FastAPI
Rule Engine
NLP / ML
Risk Engine
AI Evaluation
```

---

## 15. Định hướng AWS

Giai đoạn hiện tại ưu tiên phát triển và kiểm thử local.

Thiết kế được giữ ở trạng thái **cloud-ready** để sau này migrate:

| Hiện tại | AWS sau này |
|---|---|
| PostgreSQL | Amazon RDS PostgreSQL |
| MinIO | Amazon S3 |
| Spring Boot Docker | Amazon ECS Fargate / EC2 |
| FastAPI Docker | Amazon ECS Fargate / EC2 |
| Docker Images | Amazon ECR |
| Environment Variables | AWS Secrets Manager / Parameter Store |
| Local Logs | Amazon CloudWatch |
| JWT | Giữ nguyên hoặc Amazon Cognito |
| Whisper | Giữ nguyên hoặc đánh giá Amazon Transcribe |

Mục tiêu là chuyển infrastructure sang AWS mà hạn chế thay đổi core business logic.

---

## 16. Stack chốt

```text
Mobile:
React Native + TypeScript + Expo

Admin:
React + TypeScript + Vite + Ant Design

Backend:
Java 21 + Spring Boot 3 + Spring Security + JPA

Database:
PostgreSQL + Flyway

Storage:
MinIO

Audio:
FFmpeg

Speech-to-Text:
Whisper

AI Service:
Python + FastAPI

AI / NLP:
Transformers + PyTorch + scikit-learn
Rule Engine + Risk Engine

Testing:
JUnit + Mockito + Testcontainers + pytest + Postman

Development:
Docker + Docker Compose

Source Control:
Git + GitHub
```
