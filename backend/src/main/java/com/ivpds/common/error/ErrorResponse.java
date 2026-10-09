package com.ivpds.common.error;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.List;

/**
 * Cấu trúc JSON chung cho mọi phản hồi lỗi của API.
 *
 * @param timestamp   thời điểm xảy ra lỗi
 * @param status      mã HTTP
 * @param code        mã lỗi để client xử lý theo chương trình
 * @param message     thông báo cho người đọc
 * @param path        đường dẫn của request bị lỗi
 * @param requestId   mã request, dùng để tra log
 * @param fieldErrors danh sách lỗi theo từng trường (chỉ xuất hiện khi lỗi validation)
 */
public record ErrorResponse(
        Instant timestamp,
        int status,
        String code,
        String message,
        String path,
        String requestId,
        @JsonInclude(JsonInclude.Include.NON_EMPTY) List<FieldViolation> fieldErrors) {

    /** Lỗi của một trường dữ liệu đầu vào. */
    public record FieldViolation(String field, String message) {
    }
}
