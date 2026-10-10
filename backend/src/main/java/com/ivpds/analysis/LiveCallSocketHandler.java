package com.ivpds.analysis;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ivpds.analysis.AiClient.RiskAssessment;
import com.ivpds.analysis.LiveCallTickets.Ticket;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestOutputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;

/**
 * Luồng WebSocket của cuộc gọi trực tiếp, phía backend. Backend đứng giữa ứng dụng và AI service:
 *
 * <pre>
 *   ứng dụng  --âm thanh-->  backend  --âm thanh-->  AI service
 *   ứng dụng  <--sự kiện---  backend  <--sự kiện---  AI service
 * </pre>
 *
 * <p>Âm thanh được chuyển tiếp nguyên vẹn và đồng thời ghi ra file tạm; các sự kiện của AI service (ready,
 * transcript, risk, alert, final, error) được chuyển tiếp nguyên văn cho ứng dụng. Khi AI service gửi kết quả
 * cuối, backend lưu ghi âm vào kho lưu trữ và kết quả vào database. Nếu AI service lỗi, không trả lời, hoặc
 * ngắt giữa chừng, lần phân tích được đánh dấu FAILED kèm mã lỗi; backend không tự tạo ra điểm rủi ro nào.
 */
@Component
public class LiveCallSocketHandler extends AbstractWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(LiveCallSocketHandler.class);

    static final String TICKET_ATTRIBUTE = "liveCallTicket";
    static final int MAX_FRAME_BYTES = 1024 * 1024;
    private static final int SAMPLE_RATE = 16_000;
    private static final String END_MESSAGE = "{\"type\":\"end\"}";

    private final AiProperties ai;
    private final LiveCallRecorder recorder;
    private final ObjectMapper json;
    private final HttpClient http;
    private final Map<String, Relay> relays = new ConcurrentHashMap<>();

    public LiveCallSocketHandler(AiProperties ai, LiveCallRecorder recorder, ObjectMapper json) {
        this.ai = ai;
        this.recorder = recorder;
        this.json = json;
        this.http = HttpClient.newBuilder().connectTimeout(ai.connectTimeout()).build();
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        Ticket ticket = (Ticket) session.getAttributes().get(TICKET_ATTRIBUTE);
        Relay relay = new Relay(ticket, new ConcurrentWebSocketSessionDecorator(session, 10_000, 4 * MAX_FRAME_BYTES));
        relays.put(session.getId(), relay);
        relay.connect();
    }

    @Override
    protected void handleBinaryMessage(WebSocketSession session, BinaryMessage message) {
        Relay relay = relays.get(session.getId());
        if (relay != null) {
            relay.onAudio(message.getPayload());
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        Relay relay = relays.get(session.getId());
        if (relay != null) {
            relay.onClientText(message.getPayload());
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        Relay relay = relays.remove(session.getId());
        if (relay != null) {
            relay.onClientClosed();
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.debug("Live call transport error on session {}", session.getId(), exception);
    }

    /** Địa chỉ WebSocket của AI service, suy ra từ địa chỉ HTTP đã cấu hình. */
    private URI upstreamUri() {
        String base = ai.baseUrl().toString().replaceFirst("^http", "ws").replaceAll("/+$", "");
        return URI.create(base + "/v1/live-sessions");
    }

    /** Một cuộc gọi đang chuyển tiếp: kết nối với ứng dụng, kết nối với AI service và bản ghi âm đang ghi. */
    private final class Relay implements WebSocket.Listener {

        private final Ticket ticket;
        private final WebSocketSession client;
        private final AtomicBoolean finished = new AtomicBoolean();
        private final AtomicBoolean endRequested = new AtomicBoolean();
        private final StringBuilder partialText = new StringBuilder();
        private final Object sendLock = new Object();
        // Mỗi lần gửi sang AI service phải chờ lần trước xong, nên các lần gửi được nối thành một chuỗi.
        private CompletableFuture<WebSocket> upstream = new CompletableFuture<>();
        private final Path[] channelFiles = new Path[2];
        private final OutputStream[] channelStreams = new OutputStream[2];
        private final long[] channelBytes = new long[2];
        private final List<String> spoken = new ArrayList<>();
        private volatile String sttModel;

        Relay(Ticket ticket, WebSocketSession client) {
            this.ticket = ticket;
            this.client = client;
        }

        /** Mở kết nối tới AI service; mã theo dõi là id của lần phân tích để nối log của hai bên. */
        void connect() {
            CompletableFuture<WebSocket> connecting = http.newWebSocketBuilder()
                    .header(AiClient.API_KEY_HEADER, ai.apiKey())
                    .header(AiClient.REQUEST_ID_HEADER, ticket.analysisId().toString())
                    .connectTimeout(ai.connectTimeout())
                    .buildAsync(upstreamUri(), this);
            synchronized (sendLock) {
                upstream = connecting;
            }
            connecting.whenComplete((socket, error) -> {
                if (error != null) {
                    log.warn("Live call {}: could not reach the AI service: {}", ticket.callId(), error.toString());
                    fail(AiServiceException.UNAVAILABLE);
                }
            });
        }

        // ------------------------------------------------------- từ ứng dụng

        /** Một gói âm thanh từ ứng dụng: kiểm tra, ghi vào bản ghi âm, chuyển tiếp sang AI service. */
        void onAudio(ByteBuffer payload) {
            if (finished.get() || endRequested.get()) {
                return;
            }
            int length = payload.remaining();
            if (length < 1 || length > MAX_FRAME_BYTES || (length - 1) % 2 != 0
                    || (payload.get(payload.position()) != 0 && payload.get(payload.position()) != 1)) {
                // Gói sai định dạng: báo cho ứng dụng rồi kết thúc cuộc gọi bình thường với phần đã nhận.
                sendToClient(errorEvent("INVALID_AUDIO_FRAME",
                        "An audio frame is one byte (0 = caller, 1 = callee) followed by 16-bit PCM samples."));
                requestEnd();
                return;
            }
            byte[] bytes = new byte[length];
            payload.duplicate().get(bytes);
            record(bytes);
            sendUpstream(socket -> socket.sendBinary(ByteBuffer.wrap(bytes), true));
        }

        void onClientText(String text) {
            try {
                if ("end".equals(json.readTree(text).path("type").asText())) {
                    requestEnd();
                    return;
                }
            } catch (IOException ignored) {
                // không phải JSON: xử lý như tin nhắn sai giao thức bên dưới
            }
            sendToClient(errorEvent("INVALID_MESSAGE", "Text messages must be {\"type\": \"end\"}."));
            requestEnd();
        }

        /** Ứng dụng ngắt kết nối (cúp máy, mất mạng): vẫn kết thúc cuộc gọi và lấy kết quả cuối để lưu. */
        void onClientClosed() {
            requestEnd();
        }

        /** Báo AI service là cuộc gọi đã kết thúc, và đặt giới hạn thời gian chờ kết quả cuối. */
        private void requestEnd() {
            if (finished.get() || !endRequested.compareAndSet(false, true)) {
                return;
            }
            sendUpstream(socket -> socket.sendText(END_MESSAGE, true));
            CompletableFuture.delayedExecutor(ai.liveFinishTimeout().toMillis(), TimeUnit.MILLISECONDS)
                    .execute(() -> {
                        if (!finished.get()) {
                            log.warn("Live call {}: no final result from the AI service in time", ticket.callId());
                            fail(AiServiceException.TIMEOUT);
                        }
                    });
        }

        private void sendUpstream(java.util.function.Function<WebSocket, CompletableFuture<WebSocket>> send) {
            synchronized (sendLock) {
                upstream = upstream.thenCompose(send);
            }
        }

        // ------------------------------------------------------ từ AI service

        @Override
        public void onOpen(WebSocket webSocket) {
            webSocket.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
            partialText.append(data);
            if (last) {
                String event = partialText.toString();
                partialText.setLength(0);
                onEvent(event);
            }
            webSocket.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
            // AI service luôn gửi final hoặc error trước khi đóng; đóng mà chưa có gì là ngắt bất thường.
            if (!finished.get()) {
                log.warn("Live call {}: the AI service closed the stream early (code {})", ticket.callId(), statusCode);
                fail(AiServiceException.UNAVAILABLE);
            }
            return null;
        }

        @Override
        public void onError(WebSocket webSocket, Throwable error) {
            if (!finished.get()) {
                log.warn("Live call {}: the AI service stream failed: {}", ticket.callId(), error.toString());
                fail(AiServiceException.UNAVAILABLE);
            }
        }

        /** Một sự kiện từ AI service: xử lý phần backend cần, rồi chuyển tiếp nguyên văn cho ứng dụng. */
        private void onEvent(String event) {
            JsonNode node;
            try {
                node = json.readTree(event);
            } catch (IOException e) {
                fail(AiServiceException.INVALID_RESPONSE);
                return;
            }
            switch (node.path("type").asText()) {
                case "ready" -> sttModel = node.path("sttModel").asText(null);
                case "transcript" -> spoken.add(node.path("text").asText(""));
                case "final" -> {
                    complete(node, event);
                    return;
                }
                case "error" -> {
                    String code = node.path("code").asText("");
                    fail(code.matches("[A-Z][A-Z0-9_]{1,49}") ? code : AiServiceException.ERROR);
                    return;
                }
                default -> { }
            }
            sendToClient(event);
        }

        // ---------------------------------------------------------- kết thúc

        /** AI service đã gửi kết quả cuối: kiểm tra, lưu, rồi mới báo cho ứng dụng. */
        private void complete(JsonNode result, String event) {
            if (!finished.compareAndSet(false, true)) {
                return;
            }
            String transcript = result.path("transcript").asText("").strip();
            storeRecording();
            if (result.path("riskLevel").isNull() || transcript.isEmpty()) {
                recorder.fail(ticket.analysisId(), AnalysisProcessor.NO_SPEECH_DETECTED, null, sttModel);
            } else {
                try {
                    RiskAssessment risk = readRisk(result);
                    AiClient.validate(risk);
                    recorder.complete(ticket.analysisId(), transcript, sttModel, risk);
                } catch (AiServiceException | IllegalArgumentException e) {
                    log.warn("Live call {}: unusable final result from the AI service", ticket.callId());
                    recorder.fail(ticket.analysisId(), AiServiceException.INVALID_RESPONSE, transcript, sttModel);
                    sendToClient(errorEvent(AiServiceException.INVALID_RESPONSE,
                            AnalysisProcessor.messageFor(AiServiceException.INVALID_RESPONSE)));
                    close();
                    return;
                }
            }
            log.info("Live call {} finished: {}", ticket.callId(), result.path("riskLevel").asText("no speech"));
            sendToClient(event);
            close();
        }

        private RiskAssessment readRisk(JsonNode result) {
            List<String> indicators = new ArrayList<>();
            result.path("indicators").forEach(code -> indicators.add(code.asText()));
            JsonNode probability = result.path("modelProbability");
            return new RiskAssessment(
                    result.path("riskScore").isInt() ? result.path("riskScore").asInt() : null,
                    result.path("riskLevel").asText(null),
                    result.path("confidence").isNumber() ? result.path("confidence").asDouble() : null,
                    result.path("indicators").isArray() ? indicators : null,
                    new RiskAssessment.Components(probability.isNumber() ? probability.asDouble() : null),
                    result.path("modelVersion").asText(null), result.path("rulesetVersion").asText(null),
                    result.path("riskEngineVersion").asText(null));
        }

        /** Cuộc gọi không ra được kết quả: lưu ghi âm và phần transcript đã có, ghi mã lỗi, báo cho ứng dụng. */
        private void fail(String code) {
            if (!finished.compareAndSet(false, true)) {
                return;
            }
            storeRecording();
            recorder.fail(ticket.analysisId(), code, String.join(" ", spoken), sttModel);
            sendToClient(errorEvent(code, AnalysisProcessor.messageFor(code)));
            close();
        }

        private void close() {
            synchronized (sendLock) {
                upstream.thenAccept(socket -> {
                    if (!socket.isOutputClosed()) {
                        socket.sendClose(WebSocket.NORMAL_CLOSURE, "done");
                    }
                }).exceptionally(error -> null);
            }
            try {
                client.close(CloseStatus.NORMAL);
            } catch (IOException | RuntimeException ignored) {
                // ứng dụng có thể đã ngắt trước
            }
        }

        private void sendToClient(String text) {
            try {
                if (client.isOpen()) {
                    client.sendMessage(new TextMessage(text));
                }
            } catch (IOException | RuntimeException e) {
                log.debug("Live call {}: could not send an event to the client", ticket.callId());
            }
        }

        private String errorEvent(String code, String message) {
            return json.createObjectNode().put("type", "error").put("code", code).put("message", message).toString();
        }

        // ---------------------------------------------------------- ghi âm

        /** Ghi mẫu PCM của một gói vào file tạm của đúng người nói. */
        private synchronized void record(byte[] frame) {
            int channel = frame[0];
            try {
                if (channelStreams[channel] == null) {
                    channelFiles[channel] = Files.createTempFile("ivpds-live-", ".pcm");
                    channelStreams[channel] = new BufferedOutputStream(Files.newOutputStream(channelFiles[channel]));
                }
                channelStreams[channel].write(frame, 1, frame.length - 1);
                channelBytes[channel] += frame.length - 1;
            } catch (IOException e) {
                log.error("Live call {}: could not buffer audio", ticket.callId(), e);
            }
        }

        /**
         * Ghép hai luồng thành một file WAV hai kênh (trái: người gọi, phải: người nghe) và lưu vào kho lưu trữ.
         * Giữ hai kênh riêng để sau này vẫn biết ai nói đoạn nào. File tạm luôn được xóa.
         */
        private synchronized void storeRecording() {
            Path wav = null;
            try {
                for (OutputStream stream : channelStreams) {
                    if (stream != null) {
                        stream.close();
                    }
                }
                long samples = Math.max(channelBytes[0], channelBytes[1]) / 2;
                if (samples == 0) {
                    return;
                }
                wav = Files.createTempFile("ivpds-live-", ".wav");
                String sha256 = writeStereoWav(wav, samples);
                recorder.storeAudio(ticket.userId(), ticket.callId(), wav, Files.size(wav), sha256,
                        (double) samples / SAMPLE_RATE);
            } catch (IOException | RuntimeException e) {
                log.error("Live call {}: could not store the recording", ticket.callId(), e);
            } finally {
                for (Path file : new Path[] {channelFiles[0], channelFiles[1], wav}) {
                    if (file != null) {
                        try {
                            Files.deleteIfExists(file);
                        } catch (IOException ignored) {
                            // file tạm; hệ điều hành sẽ dọn
                        }
                    }
                }
            }
        }

        /** Viết file WAV PCM 16 bit, 16 kHz, hai kênh; kênh ngắn hơn được bù im lặng. Trả về SHA-256 của file. */
        private String writeStereoWav(Path target, long samples) throws IOException {
            MessageDigest digest;
            try {
                digest = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException("SHA-256 is not available", e);
            }
            long dataBytes = samples * 4;
            ByteBuffer header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
            header.put("RIFF".getBytes(StandardCharsets.US_ASCII)).putInt((int) (36 + dataBytes))
                    .put("WAVE".getBytes(StandardCharsets.US_ASCII))
                    .put("fmt ".getBytes(StandardCharsets.US_ASCII)).putInt(16)
                    .putShort((short) 1).putShort((short) 2).putInt(SAMPLE_RATE).putInt(SAMPLE_RATE * 4)
                    .putShort((short) 4).putShort((short) 16)
                    .put("data".getBytes(StandardCharsets.US_ASCII)).putInt((int) dataBytes);
            try (OutputStream out = new DigestOutputStream(new BufferedOutputStream(Files.newOutputStream(target)),
                    digest);
                    InputStream left = open(channelFiles[0]);
                    InputStream right = open(channelFiles[1])) {
                out.write(header.array());
                byte[] a = new byte[2];
                byte[] b = new byte[2];
                for (long i = 0; i < samples; i++) {
                    readSample(left, a);
                    readSample(right, b);
                    out.write(a);
                    out.write(b);
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        }

        private InputStream open(Path file) throws IOException {
            return file == null ? InputStream.nullInputStream() : new java.io.BufferedInputStream(Files.newInputStream(file));
        }

        /** Đọc một mẫu 16 bit; hết dữ liệu thì trả về im lặng. */
        private void readSample(InputStream in, byte[] sample) throws IOException {
            if (in.readNBytes(sample, 0, 2) < 2) {
                sample[0] = 0;
                sample[1] = 0;
            }
        }
    }
}
