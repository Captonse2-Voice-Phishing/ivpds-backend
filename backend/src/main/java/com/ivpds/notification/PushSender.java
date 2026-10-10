package com.ivpds.notification;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * Gửi thông báo đẩy tới thiết bị của người dùng qua Expo Push Service.
 *
 * <p>Thông báo luôn được lưu trong database trước; kênh đẩy chỉ là cách báo thêm cho người dùng khi ứng dụng không
 * mở. Vì vậy mọi lỗi ở đây (Expo không phản hồi, token hỏng, hàng chờ đầy) chỉ được ghi log và không bao giờ ảnh
 * hưởng tới thông báo đã lưu hay tới kết quả phân tích. Việc gửi chạy trên luồng riêng để không làm chậm luồng đã
 * tạo ra thông báo.
 */
@Component
public class PushSender {

    private static final Logger log = LoggerFactory.getLogger(PushSender.class);
    /** Expo nhận tối đa 100 tin trong một yêu cầu. */
    private static final int BATCH_SIZE = 100;
    /** Mã lỗi Expo trả về khi token không còn thuộc về lần cài ứng dụng nào. */
    private static final String DEVICE_NOT_REGISTERED = "DeviceNotRegistered";

    private final PushProperties properties;
    private final PushDeviceRepository devices;
    private final ObjectMapper json;
    private final HttpClient http;
    private final ThreadPoolTaskExecutor executor;

    public PushSender(PushProperties properties, PushDeviceRepository devices, ObjectMapper json) {
        this.properties = properties;
        this.devices = devices;
        this.json = json;
        this.http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(properties.connectTimeout()).build();
        // Bộ thực thi riêng của module, không đăng ký làm bean để không thay thế bộ thực thi mặc định của Spring.
        this.executor = new ThreadPoolTaskExecutor();
        this.executor.setThreadNamePrefix("push-");
        this.executor.setCorePoolSize(1);
        this.executor.setMaxPoolSize(1);
        this.executor.setQueueCapacity(500);
        this.executor.initialize();
    }

    @PreDestroy
    void shutdown() {
        executor.shutdown();
    }

    /**
     * Khi một thông báo đã được lưu chắc chắn (sau khi giao dịch tạo ra nó commit), xếp việc gửi vào hàng chờ.
     * {@code fallbackExecution} để sự kiện phát ra ngoài giao dịch cũng được xử lý.
     */
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT, fallbackExecution = true)
    public void onNotificationCreated(NotificationCreatedEvent event) {
        if (!properties.enabled()) {
            return;
        }
        try {
            executor.execute(() -> deliver(event));
        } catch (TaskRejectedException e) {
            log.warn("Push queue is full; notification {} was not pushed", event.notificationId());
        }
    }

    /** Gửi một thông báo tới mọi thiết bị của người nhận. */
    void deliver(NotificationCreatedEvent event) {
        try {
            List<String> tokens = devices.findByUserIdOrderByLastSeenAtDesc(event.userId()).stream()
                    .map(PushDevice::getToken).toList();
            for (int from = 0; from < tokens.size(); from += BATCH_SIZE) {
                send(event, tokens.subList(from, Math.min(from + BATCH_SIZE, tokens.size())));
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (IOException | RuntimeException e) {
            log.warn("Could not push notification {}: {}", event.notificationId(), e.toString());
        }
    }

    private void send(NotificationCreatedEvent event, List<String> tokens) throws IOException, InterruptedException {
        ArrayNode messages = json.createArrayNode();
        for (String token : tokens) {
            ObjectNode message = messages.addObject();
            message.put("to", token);
            message.put("title", event.title());
            message.put("body", event.message());
            message.put("sound", "default");
            message.put("priority", "high");
            // Dữ liệu để ứng dụng mở đúng màn hình khi người dùng bấm vào thông báo.
            ObjectNode data = message.putObject("data");
            data.put("notificationId", event.notificationId().toString());
            data.put("type", event.type().name());
            data.put("callId", event.callId() == null ? null : event.callId().toString());
            data.put("analysisId", event.analysisId() == null ? null : event.analysisId().toString());
        }
        HttpRequest.Builder request = HttpRequest.newBuilder(properties.url())
                .timeout(properties.requestTimeout())
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(messages), StandardCharsets.UTF_8));
        if (properties.accessToken() != null && !properties.accessToken().isBlank()) {
            request.header("Authorization", "Bearer " + properties.accessToken());
        }
        HttpResponse<String> response = http.send(request.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (response.statusCode() != 200) {
            log.warn("Push service answered {} for notification {}", response.statusCode(), event.notificationId());
            return;
        }
        removeDeadTokens(event, tokens, json.readTree(response.body()).path("data"));
    }

    /** Expo trả một "ticket" cho mỗi tin, theo đúng thứ tự gửi; token bị báo không còn đăng ký thì xóa. */
    private void removeDeadTokens(NotificationCreatedEvent event, List<String> tokens, JsonNode tickets) {
        List<String> dead = new ArrayList<>();
        int failed = 0;
        for (int i = 0; i < tokens.size() && i < tickets.size(); i++) {
            JsonNode ticket = tickets.get(i);
            if ("ok".equals(ticket.path("status").asText())) {
                continue;
            }
            failed++;
            if (DEVICE_NOT_REGISTERED.equals(ticket.path("details").path("error").asText())) {
                dead.add(tokens.get(i));
            }
        }
        if (!dead.isEmpty()) {
            devices.deleteByTokenIn(dead);
        }
        log.info("Pushed notification {} to {} device(s), {} refused, {} removed", event.notificationId(),
                tokens.size(), failed, dead.size());
    }
}
