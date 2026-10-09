package com.ivpds.common.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Gắn một mã request (request id) cho mỗi request, đưa mã đó vào mọi dòng log qua MDC,
 * trả lại trong header {@code X-Request-Id}, và ghi một dòng access log cho mỗi request.
 * Nếu client gửi sẵn header {@code X-Request-Id} hợp lệ thì dùng lại mã đó.
 */
@Component
// Chạy trước mọi filter khác (kể cả Spring Security) để lỗi 401/403 cũng có mã request.
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestLoggingFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-Id";
    public static final String MDC_KEY = "requestId";

    private static final Logger log = LoggerFactory.getLogger(RequestLoggingFilter.class);

    // Mã do client gửi sẽ được ghi vào log, nên chỉ chấp nhận tập ký tự an toàn để tránh chèn nội dung vào log.
    private static final Pattern SAFE_ID = Pattern.compile("[A-Za-z0-9._-]{1,64}");

    /** Đặt mã request trước khi xử lý, ghi access log sau khi xử lý, rồi dọn MDC. */
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String requestId = resolveRequestId(request.getHeader(HEADER));
        MDC.put(MDC_KEY, requestId);
        response.setHeader(HEADER, requestId);
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long millis = (System.nanoTime() - start) / 1_000_000;
            // Health check gọi liên tục nên chỉ ghi ở mức DEBUG để không làm ngập log.
            if (request.getRequestURI().startsWith("/actuator")) {
                log.debug("{} {} -> {} ({} ms)", request.getMethod(), request.getRequestURI(), response.getStatus(),
                        millis);
            } else {
                log.info("{} {} -> {} ({} ms)", request.getMethod(), request.getRequestURI(), response.getStatus(),
                        millis);
            }
            MDC.remove(MDC_KEY);
        }
    }

    /** Dùng lại mã của client nếu hợp lệ, ngược lại sinh mã UUID mới. */
    private static String resolveRequestId(String header) {
        if (header != null && SAFE_ID.matcher(header).matches()) {
            return header;
        }
        return UUID.randomUUID().toString();
    }
}
