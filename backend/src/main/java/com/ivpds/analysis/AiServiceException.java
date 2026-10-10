package com.ivpds.analysis;

/**
 * Lỗi khi gọi AI service. Mỗi lỗi mang một mã cố định để lưu vào {@code analyses.error_code};
 * lỗi này không bao giờ được chuyển thành một kết quả đánh giá rủi ro.
 */
public class AiServiceException extends RuntimeException {

    /** Không kết nối được tới AI service (service tắt, sai địa chỉ, mạng lỗi). */
    public static final String UNAVAILABLE = "AI_SERVICE_UNAVAILABLE";
    /** AI service không trả lời trong thời gian cho phép. */
    public static final String TIMEOUT = "AI_SERVICE_TIMEOUT";
    /** AI service trả lỗi 5xx không rõ nguyên nhân. */
    public static final String ERROR = "AI_SERVICE_ERROR";
    /** AI service từ chối khóa API của backend (lỗi cấu hình). */
    public static final String AUTH_FAILED = "AI_SERVICE_AUTH_FAILED";
    /** AI service trả về nội dung không đọc được hoặc thiếu, sai giá trị. */
    public static final String INVALID_RESPONSE = "AI_INVALID_RESPONSE";
    /** AI service từ chối yêu cầu với một mã 4xx không nằm trong danh sách đã biết. */
    public static final String REQUEST_REJECTED = "AI_REQUEST_REJECTED";

    private final String code;

    /**
     * @param code    mã lỗi: một trong các hằng số ở trên, hoặc mã do chính AI service trả về
     *                (ví dụ INVALID_AUDIO, STT_UNAVAILABLE, NLP_MODEL_UNAVAILABLE)
     * @param message mô tả cho log; không trả nguyên văn cho client
     */
    public AiServiceException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
