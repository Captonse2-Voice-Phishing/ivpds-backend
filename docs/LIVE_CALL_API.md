# API phân tích cuộc gọi trực tiếp (Live Call)

Tài liệu cho người làm ứng dụng mobile. API này cho phép ứng dụng gửi âm thanh của một cuộc gọi VoIP **đang diễn ra** và nhận transcript, điểm rủi ro, cảnh báo ngay trong lúc gọi.

Đây là phần mở rộng ngoài README (Phase 11B). Phần thiết lập cuộc gọi VoIP giữa hai máy (đổ chuông, truyền tiếng cho nhau) do ứng dụng tự làm; API này chỉ lo việc phân tích.

## 1. Trình tự

```text
1. Cuộc gọi bắt đầu
   POST /api/v1/live-calls            (Bearer token)   ->  callId, ticket, streamPath

2. Mở WebSocket
   ws(s)://<backend><streamPath>?ticket=<ticket>       <-  {"type":"ready", ...}

3. Trong lúc gọi
   gửi: gói âm thanh nhị phân của hai bên, liên tục
   nhận: transcript, risk, alert

4. Cuộc gọi kết thúc
   gửi: {"type":"end"}                                 <-  {"type":"final", ...}, rồi server đóng kết nối

5. Xem lại sau này
   GET /api/v1/calls/{callId}/analyses/latest
   GET /api/v1/calls/{callId}/audio
```

## 2. Mở cuộc gọi

`POST /api/v1/live-calls`, cần `Authorization: Bearer <accessToken>`.

Body (tùy chọn):

```json
{ "callerNumber": "0901234567" }
```

Trả về `201`:

```json
{
  "callId": "…",
  "analysisId": "…",
  "streamPath": "/api/v1/live-calls/stream",
  "ticket": "chuỗi-ngẫu-nhiên",
  "ticketExpiresInSeconds": 60,
  "audioFormat": {
    "encoding": "pcm_s16le",
    "sampleRate": 16000,
    "channels": 1,
    "speakerPrefix": { "0": "CALLER", "1": "CALLEE" }
  }
}
```

- `ticket` chỉ dùng được **một lần** và hết hạn sau 60 giây nếu chưa dùng. Mỗi cuộc gọi lấy một vé mới.
- WebSocket không dùng Bearer token; quyền truy cập do vé quyết định. Mở WebSocket không có vé hợp lệ nhận HTTP 401.

## 3. Gửi âm thanh

Mỗi tin nhắn **nhị phân** là một gói âm thanh:

| Byte | Nội dung |
|---|---|
| 0 | Người nói: `0` = người gọi đến (tiếng nhận về từ đầu dây bên kia), `1` = người dùng ứng dụng (tiếng micro) |
| 1… | Mẫu PCM 16 bit có dấu, little-endian, một kênh, 16 kHz |

Quy tắc:

- **Gửi cả hai luồng liên tục từ lúc cuộc gọi bắt đầu, kể cả khi im lặng.** Thời điểm của mỗi câu được tính theo lượng âm thanh đã gửi trên luồng của người đó; nếu chỉ gửi khi có tiếng thì thứ tự các câu giữa hai bên sẽ sai.
- Gói dài 100–500 ms là hợp lý (3.200–16.000 byte dữ liệu). Tối đa 1 MB một gói.
- Số byte dữ liệu phải chẵn (trọn mẫu 16 bit).
- Nếu ứng dụng thu ở tần số khác (ví dụ 48 kHz), phải đổi về 16 kHz một kênh trước khi gửi.

## 4. Sự kiện nhận về

Mỗi tin nhắn **văn bản** từ server là một JSON có trường `type`. Số thứ tự `seq` tăng dần.

### `ready`
Gửi một lần ngay sau khi kết nối. Từ lúc này mới gửi âm thanh.

### `transcript`
Một câu vừa được nhận dạng.

```json
{ "type": "transcript", "seq": 5, "speaker": "CALLER", "start": 12.4, "end": 16.1, "text": "anh đọc mã otp cho em" }
```

`start` và `end` là giây tính từ đầu luồng của người nói đó.

### `risk`
Điểm rủi ro của **cả cuộc gọi tính đến lúc này**, gửi sau mỗi câu mới.

```json
{ "type": "risk", "seq": 6, "riskScore": 97, "riskLevel": "HIGH", "confidence": 0.87,
  "indicators": ["OTP_REQUEST", "URGENCY"], "newIndicators": ["OTP_REQUEST"], "modelProbability": 0.9999 }
```

- `riskLevel`: `LOW` (0–29), `MEDIUM` (30–59), `HIGH` (60–100).
- `confidence` là mức chắc chắn của kết quả, không phải xác suất lừa đảo.
- `newIndicators`: các dấu hiệu mới xuất hiện ở câu vừa rồi.

### `alert`
Mức rủi ro **vừa tăng** lên `MEDIUM` hoặc `HIGH`. Đây là lúc ứng dụng nên rung, phát âm báo hoặc hiện cảnh báo.

```json
{ "type": "alert", "seq": 7, "riskLevel": "HIGH", "riskScore": 97, "confidence": 0.87,
  "indicators": ["OTP_REQUEST", "URGENCY"], "modelProbability": 0.9999, "atSeconds": 16.1,
  "triggeredBy": { "speaker": "CALLER", "text": "anh đọc mã otp cho em" } }
```

Mỗi mức chỉ được báo một lần trong một cuộc gọi: tối đa một `alert` MEDIUM và một `alert` HIGH. Điểm dao động quanh ngưỡng không gây cảnh báo lặp lại.

### `final`
Kết quả chốt sau khi cuộc gọi kết thúc. Sau sự kiện này server đóng kết nối (mã 1000).

```json
{ "type": "final", "seq": 40, "endedBy": "CLIENT", "durationSeconds": 183.2,
  "riskScore": 97, "riskLevel": "HIGH", "confidence": 0.87, "indicators": ["…"], "modelProbability": 0.9999,
  "transcript": "toàn bộ nội dung…",
  "turns": [ { "speaker": "CALLEE", "start": 0.4, "end": 1.9, "text": "a lô" } ],
  "modelVersion": "…", "rulesetVersion": "…", "riskEngineVersion": "…" }
```

- `endedBy`: `CLIENT` (ứng dụng gửi `end` hoặc ngắt kết nối), `IDLE_TIMEOUT` (30 giây không nhận được gì), `MAX_DURATION` (cuộc gọi dài quá 30 phút).
- Nếu không nhận ra câu nào, `riskScore`, `riskLevel`, `confidence` là `null`: không có kết quả thì không có mức rủi ro.

### `error`
Phiên không thể tiếp tục; sau đó server đóng kết nối.

```json
{ "type": "error", "code": "AI_SERVICE_UNAVAILABLE", "message": "…" }
```

| `code` | Ý nghĩa | Ứng dụng nên làm |
|---|---|---|
| `AI_SERVICE_UNAVAILABLE` | Không kết nối được AI service, hoặc nó ngắt giữa chừng | Báo người dùng là không phân tích được; cuộc gọi vẫn tiếp tục |
| `AI_SERVICE_TIMEOUT` | Đã kết thúc cuộc gọi nhưng không nhận được kết quả cuối | Xem lại sau qua API lịch sử |
| `STT_UNAVAILABLE`, `NLP_MODEL_UNAVAILABLE` | Model chưa nạp được | Như trên |
| `LIVE_SESSION_LIMIT` | Đang có quá nhiều cuộc gọi được phân tích | Thử lại ở cuộc gọi sau |
| `LIVE_SESSION_OVERLOADED` | Máy chủ không nhận dạng kịp tốc độ nói | Như trên |
| `INVALID_AUDIO_FRAME`, `INVALID_MESSAGE` | Ứng dụng gửi sai định dạng | Lỗi lập trình phía ứng dụng |
| `AI_INVALID_RESPONSE` | AI service trả kết quả không dùng được | Báo lỗi |

Riêng `INVALID_AUDIO_FRAME` và `INVALID_MESSAGE`: sau sự kiện `error`, server vẫn kết thúc cuộc gọi bình thường và gửi `final` cho phần đã nhận.

## 5. Kết thúc cuộc gọi

Gửi tin nhắn văn bản `{"type":"end"}`. Server nhận dạng nốt câu đang nói dở, gửi `final`, rồi đóng kết nối.

Nếu ứng dụng ngắt kết nối mà không gửi `end` (mất mạng, bị tắt), backend tự kết thúc và vẫn lưu kết quả.

## 6. Sau cuộc gọi

Cuộc gọi trực tiếp được lưu như mọi cuộc gọi khác, với `source` là `LIVE`:

- `GET /api/v1/calls/{callId}/analyses/latest`: trạng thái `COMPLETED` kèm transcript, điểm, mức rủi ro, dấu hiệu; hoặc `FAILED` kèm `errorCode`.
- `GET /api/v1/calls/{callId}/audio`: ghi âm dạng WAV hai kênh (trái: người gọi, phải: người dùng).
- `POST /api/v1/calls/{callId}/analyses`: phân tích lại ghi âm đó như một file, ví dụ khi phân tích trực tiếp bị lỗi giữa chừng.

## 7. Giới hạn hiện tại

| Giới hạn | Giá trị mặc định |
|---|---|
| Số cuộc gọi được phân tích cùng lúc | 2 |
| Thời lượng tối đa một cuộc gọi | 30 phút |
| Im lặng trên kết nối trước khi tự đóng | 30 giây |
| Độ trễ từ lúc nói xong tới lúc có chữ | đo trên CPU của máy phát triển với một cuộc gọi thật 150 giây: trung vị 4,6 giây, lớn nhất 7,3 giây |

Nhận dạng giọng nói chạy trên CPU nên chỉ phục vụ được ít cuộc gọi cùng lúc; muốn nhiều hơn cần GPU.

Các mẫu lừa đảo đang bật của quản trị viên được backend tự gửi cho AI service khi mở mỗi cuộc gọi; ứng dụng không cần làm gì thêm. Dấu hiệu do mẫu tạo ra xuất hiện trong `indicators` như mọi dấu hiệu khác.

## 8. Thử nhanh khi chưa có ứng dụng

`ai/tools/live_call_demo.py` đóng vai ứng dụng: phát một file âm thanh qua API này đúng tốc độ thời gian thực và in các sự kiện.

```bash
ffmpeg -i call.m4a -f s16le -ar 16000 -ac 1 call.raw
pip install websockets
python ai/tools/live_call_demo.py --audio call.raw --email you@example.com --password ...
```

## 9. Ví dụ phía ứng dụng (TypeScript)

```ts
const opened = await api.post('/api/v1/live-calls', { callerNumber });
const socket = new WebSocket(`${WS_BASE}${opened.streamPath}?ticket=${opened.ticket}`);
socket.binaryType = 'arraybuffer';

socket.onmessage = (message) => {
  const event = JSON.parse(message.data as string);
  if (event.type === 'alert') showWarning(event.riskLevel, event.triggeredBy.text);
  if (event.type === 'risk') updateRiskBadge(event.riskScore, event.riskLevel);
  if (event.type === 'final' || event.type === 'error') socket.close();
};

// speaker: 0 = tiếng nhận về, 1 = tiếng micro; pcm: Int16Array 16 kHz mono
function sendAudio(speaker: 0 | 1, pcm: Int16Array) {
  const packet = new Uint8Array(1 + pcm.byteLength);
  packet[0] = speaker;
  packet.set(new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength), 1);
  socket.send(packet);
}

function hangUp() {
  socket.send(JSON.stringify({ type: 'end' }));
}
```
