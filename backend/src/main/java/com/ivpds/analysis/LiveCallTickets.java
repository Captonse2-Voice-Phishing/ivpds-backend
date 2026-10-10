package com.ivpds.analysis;

import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Vé dùng một lần để mở luồng WebSocket của một cuộc gọi trực tiếp.
 *
 * <p>Trình duyệt và nhiều thư viện mobile không gửi được header Authorization khi mở WebSocket, còn đưa access
 * token lên URL thì token dễ lọt vào log. Vì vậy client lấy vé qua một API có đăng nhập, rồi mở WebSocket kèm vé.
 * Vé là chuỗi ngẫu nhiên, chỉ dùng được một lần và hết hạn sau thời gian ngắn. Vé nằm trong bộ nhớ của một tiến
 * trình backend.
 */
@Component
public class LiveCallTickets {

    /** Cuộc gọi mà một vé cho phép truyền âm thanh. */
    public record Ticket(UUID callId, UUID analysisId, UUID userId, Instant expiresAt) {
    }

    private final SecureRandom random = new SecureRandom();
    private final Map<String, Ticket> tickets = new ConcurrentHashMap<>();
    private final Duration ttl;

    public LiveCallTickets(@Value("${ivpds.live.ticket-ttl}") Duration ttl) {
        this.ttl = ttl;
    }

    public Duration ttl() {
        return ttl;
    }

    /** Phát một vé mới cho cuộc gọi vừa mở. */
    public String issue(UUID callId, UUID analysisId, UUID userId) {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String value = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        tickets.put(value, new Ticket(callId, analysisId, userId, Instant.now().plus(ttl)));
        return value;
    }

    /** Dùng một vé: trả về cuộc gọi của vé nếu vé tồn tại và còn hạn. Vé bị xóa dù còn hạn hay không. */
    public Optional<Ticket> consume(String value) {
        if (value == null) {
            return Optional.empty();
        }
        Ticket ticket = tickets.remove(value);
        return ticket != null && ticket.expiresAt().isAfter(Instant.now()) ? Optional.of(ticket) : Optional.empty();
    }

    /** Lấy ra và xóa các vé đã hết hạn mà chưa ai dùng; cuộc gọi của chúng sẽ không bao giờ bắt đầu. */
    public List<Ticket> removeExpired() {
        Instant now = Instant.now();
        List<Ticket> expired = new ArrayList<>();
        tickets.forEach((value, ticket) -> {
            if (!ticket.expiresAt().isAfter(now) && tickets.remove(value, ticket)) {
                expired.add(ticket);
            }
        });
        return expired;
    }
}
