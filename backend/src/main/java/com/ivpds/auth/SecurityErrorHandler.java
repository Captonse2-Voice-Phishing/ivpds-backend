package com.ivpds.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ivpds.common.error.ErrorResponse;
import com.ivpds.common.logging.RequestLoggingFilter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

/**
 * Ghi phản hồi 401 và 403 từ chuỗi filter bảo mật theo đúng cấu trúc lỗi chung.
 * Các lỗi này xảy ra trước khi request tới controller nên GlobalExceptionHandler không bắt được.
 */
@Component
public class SecurityErrorHandler implements AuthenticationEntryPoint, AccessDeniedHandler {

    private final ObjectMapper objectMapper;

    public SecurityErrorHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /** Chưa đăng nhập, hoặc token thiếu, sai, hết hạn: trả 401. */
    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response, AuthenticationException ex)
            throws IOException {
        write(request, response, HttpStatus.UNAUTHORIZED, "Authentication is required or the token is invalid.");
    }

    /** Đã đăng nhập nhưng không đủ quyền (ví dụ USER gọi API của ADMIN): trả 403. */
    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response, AccessDeniedException ex)
            throws IOException {
        write(request, response, HttpStatus.FORBIDDEN, "You do not have permission to access this resource.");
    }

    /** Ghi phản hồi lỗi dạng JSON trực tiếp vào response. */
    private void write(HttpServletRequest request, HttpServletResponse response, HttpStatus status, String message)
            throws IOException {
        ErrorResponse body = new ErrorResponse(Instant.now(), status.value(), status.name(), message,
                request.getRequestURI(), MDC.get(RequestLoggingFilter.MDC_KEY), List.of());
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(response.getOutputStream(), body);
    }
}
