package com.ivpds.common.error;

import com.ivpds.common.error.ErrorResponse.FieldViolation;
import com.ivpds.common.logging.RequestLoggingFilter;
import jakarta.validation.ConstraintViolationException;
import java.time.Instant;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

/**
 * Bộ xử lý lỗi toàn cục: mọi exception phát sinh khi xử lý request đều được chuyển thành
 * {@link ErrorResponse}, để client luôn nhận cùng một cấu trúc lỗi.
 */
@RestControllerAdvice
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    static final String VALIDATION_FAILED = "VALIDATION_FAILED";
    static final String MALFORMED_REQUEST = "MALFORMED_REQUEST";
    static final String INTERNAL_ERROR = "INTERNAL_ERROR";

    private static final String INTERNAL_ERROR_MESSAGE = "An unexpected error occurred.";

    /** Lỗi nghiệp vụ do các module chủ động ném ra: giữ nguyên mã HTTP, mã lỗi và thông báo. */
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Object> handleApiException(ApiException ex, WebRequest request) {
        return build(ex.getStatus(), ex.getCode(), ex.getMessage(), List.of(), new HttpHeaders(), request);
    }

    /** Lỗi validation trên tham số của method (query, path): trả 400 kèm danh sách vi phạm. */
    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<Object> handleConstraintViolation(ConstraintViolationException ex, WebRequest request) {
        List<FieldViolation> violations = ex.getConstraintViolations().stream()
                .map(v -> new FieldViolation(v.getPropertyPath().toString(), v.getMessage()))
                .toList();
        return build(HttpStatus.BAD_REQUEST, VALIDATION_FAILED, "Request validation failed.", violations,
                new HttpHeaders(), request);
    }

    /**
     * Mọi lỗi không lường trước: ghi log đầy đủ ở server nhưng chỉ trả cho client thông báo chung,
     * không lộ chi tiết nội bộ (tên exception, stack trace, câu SQL...).
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Object> handleUnexpected(Exception ex, WebRequest request) {
        log.error("Unhandled exception", ex);
        return build(HttpStatus.INTERNAL_SERVER_ERROR, INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE, List.of(),
                new HttpHeaders(), request);
    }

    /** Lỗi validation trên body JSON (@Valid): trả 400 kèm lỗi của từng trường. */
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        List<FieldViolation> violations = ex.getBindingResult().getFieldErrors().stream()
                .map(e -> new FieldViolation(e.getField(), e.getDefaultMessage()))
                .toList();
        return build(status, VALIDATION_FAILED, "Request validation failed.", violations, headers, request);
    }

    /** Body thiếu hoặc không phải JSON hợp lệ: trả 400, không lộ thông báo của bộ phân tích JSON. */
    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(HttpMessageNotReadableException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        return build(status, MALFORMED_REQUEST, "Request body is missing or malformed.", List.of(), headers,
                request);
    }

    /**
     * Xử lý chung cho mọi lỗi còn lại của Spring MVC (404, 405, 415, thiếu tham số...).
     * Mã lỗi lấy theo tên mã HTTP (ví dụ NOT_FOUND); lỗi 5xx thì trả thông báo chung.
     */
    @Override
    protected ResponseEntity<Object> handleExceptionInternal(Exception ex, Object body, HttpHeaders headers,
            HttpStatusCode status, WebRequest request) {
        if (status.is5xxServerError()) {
            log.error("Request failed with {}", status, ex);
            return build(status, INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE, List.of(), headers, request);
        }
        HttpStatus resolved = HttpStatus.resolve(status.value());
        String code = resolved != null ? resolved.name() : "HTTP_" + status.value();
        String message = body instanceof ProblemDetail detail && detail.getDetail() != null
                ? detail.getDetail()
                : (resolved != null ? resolved.getReasonPhrase() : "Request failed.");
        return build(status, code, message, List.of(), headers, request);
    }

    /** Tạo phản hồi lỗi theo cấu trúc chung, gắn kèm đường dẫn và mã request hiện tại. */
    private ResponseEntity<Object> build(HttpStatusCode status, String code, String message,
            List<FieldViolation> violations, HttpHeaders headers, WebRequest request) {
        String path = request instanceof ServletWebRequest servlet ? servlet.getRequest().getRequestURI() : null;
        ErrorResponse body = new ErrorResponse(Instant.now(), status.value(), code, message, path,
                MDC.get(RequestLoggingFilter.MDC_KEY), violations);
        return ResponseEntity.status(status).headers(headers).body(body);
    }
}
