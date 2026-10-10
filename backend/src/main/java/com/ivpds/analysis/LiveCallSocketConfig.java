package com.ivpds.analysis;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.server.HandshakeInterceptor;
import org.springframework.web.socket.server.standard.ServletServerContainerFactoryBean;
import org.springframework.web.util.UriComponentsBuilder;

/** Đăng ký điểm WebSocket của cuộc gọi trực tiếp và kiểm tra vé khi client mở kết nối. */
@Configuration
@EnableWebSocket
public class LiveCallSocketConfig implements WebSocketConfigurer {

    private final LiveCallSocketHandler handler;
    private final LiveCallTickets tickets;

    public LiveCallSocketConfig(LiveCallSocketHandler handler, LiveCallTickets tickets) {
        this.handler = handler;
        this.tickets = tickets;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, LiveCallController.STREAM_PATH)
                .addInterceptors(new TicketInterceptor())
                // Ứng dụng mobile không gửi header Origin; quyền truy cập do vé quyết định, không do nguồn gốc trang.
                .setAllowedOriginPatterns("*");
    }

    /** Cho phép gói âm thanh tới 1 MB; mặc định của máy chủ chỉ là 8 KB. */
    @Bean
    ServletServerContainerFactoryBean liveCallSocketContainer() {
        ServletServerContainerFactoryBean container = new ServletServerContainerFactoryBean();
        container.setMaxBinaryMessageBufferSize(LiveCallSocketHandler.MAX_FRAME_BYTES + 16);
        container.setMaxTextMessageBufferSize(64 * 1024);
        return container;
    }

    /** Chỉ chấp nhận kết nối có vé hợp lệ ở tham số {@code ticket}; vé bị dùng mất ngay tại đây. */
    private final class TicketInterceptor implements HandshakeInterceptor {

        @Override
        public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                WebSocketHandler wsHandler, Map<String, Object> attributes) {
            String value = UriComponentsBuilder.fromUri(request.getURI()).build().getQueryParams().getFirst("ticket");
            return tickets.consume(value).map(ticket -> {
                attributes.put(LiveCallSocketHandler.TICKET_ATTRIBUTE, ticket);
                return true;
            }).orElseGet(() -> {
                response.setStatusCode(HttpStatus.UNAUTHORIZED);
                return false;
            });
        }

        @Override
        public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response, WebSocketHandler wsHandler,
                Exception exception) {
            // không có gì để làm sau khi bắt tay
        }
    }
}
