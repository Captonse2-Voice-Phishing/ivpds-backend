package com.ivpds.common.error;

import org.springframework.http.HttpStatus;

/**
 * Lỗi nghiệp vụ có chủ đích (ví dụ: sai mật khẩu, không tìm thấy cuộc gọi).
 * Các module ném lỗi này kèm mã lỗi riêng; thông báo (message) được trả nguyên văn cho client.
 */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    /**
     * @param status  mã HTTP trả về cho client
     * @param code    mã lỗi để client xử lý theo chương trình (ví dụ INVALID_CREDENTIALS)
     * @param message thông báo cho người đọc
     */
    public ApiException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }
}
