package com.ivpds.analysis;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;

/**
 * A local HTTP server that stands in for the AI service in tests. It is not an AI: each test tells it
 * exactly what to answer, so the backend's handling of every kind of answer and failure can be checked.
 * Whether the real AI service works is verified separately, against the real service.
 */
public final class StubAiServer implements AutoCloseable {

    /** What the stub does with one request. */
    @FunctionalInterface
    public interface Behaviour {
        void handle(HttpExchange exchange, byte[] requestBody) throws IOException;
    }

    /** One request the stub received. */
    public record Received(String path, String apiKey, String requestId, String contentType, byte[] body) {
    }

    public static final String TRANSCRIPT = "Tôi gọi từ ngân hàng. Anh đọc mã OTP tôi vừa gửi.";

    private final HttpServer server;
    private final List<Received> received = new CopyOnWriteArrayList<>();
    private volatile Behaviour transcription;
    private volatile Behaviour risk;

    public StubAiServer() {
        try {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        server.setExecutor(Executors.newCachedThreadPool());
        server.createContext("/v1/transcriptions", exchange -> dispatch(exchange, transcription));
        server.createContext("/v1/risk-assessments", exchange -> dispatch(exchange, risk));
        server.start();
        reset();
    }

    public String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    /** Back to answering both endpoints successfully, with no recorded requests. */
    public void reset() {
        received.clear();
        transcription = json(200, transcriptionBody(TRANSCRIPT));
        risk = json(200, riskBody(100, "HIGH", 1.0));
    }

    public void onTranscription(Behaviour behaviour) {
        this.transcription = behaviour;
    }

    public void onRisk(Behaviour behaviour) {
        this.risk = behaviour;
    }

    public List<Received> received() {
        return List.copyOf(received);
    }

    public List<Received> received(String path) {
        return received.stream().filter(request -> request.path().equals(path)).toList();
    }

    @Override
    public void close() {
        server.stop(0);
    }

    private void dispatch(HttpExchange exchange, Behaviour behaviour) throws IOException {
        try (exchange) {
            byte[] body = exchange.getRequestBody().readAllBytes();
            received.add(new Received(exchange.getRequestURI().getPath(),
                    exchange.getRequestHeaders().getFirst("X-API-Key"),
                    exchange.getRequestHeaders().getFirst("X-Request-Id"),
                    exchange.getRequestHeaders().getFirst("Content-Type"), body));
            behaviour.handle(exchange, body);
        }
    }

    // ------------------------------------------------------------- behaviours

    /** Answer with a JSON body. */
    public static Behaviour json(int status, String body) {
        return raw(status, "application/json", body);
    }

    /** Answer with any body and content type. */
    public static Behaviour raw(int status, String contentType, String body) {
        return (exchange, request) -> {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", contentType);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        };
    }

    /** Answer the way the AI service reports an error. */
    public static Behaviour error(int status, String code) {
        return json(status, """
                {"timestamp":"2026-10-10T00:00:00Z","status":%d,"code":"%s","message":"stub","path":"/v1","requestId":null}
                """.formatted(status, code));
    }

    /** Wait before answering, to trigger the client's timeout. */
    public static Behaviour delayed(long millis, Behaviour then) {
        return (exchange, request) -> {
            try {
                Thread.sleep(millis);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            then.handle(exchange, request);
        };
    }

    /** Close the connection without sending anything, as a crashing service would. */
    public static Behaviour dropConnection() {
        return (exchange, request) -> exchange.close();
    }

    // ------------------------------------------------------------------ bodies

    public static String transcriptionBody(String transcript) {
        return """
                {"transcript":%s,"language":"vi","sttModel":"stub-whisper",
                 "audio":{"container":"wav","codec":"pcm_s16le","sampleRate":16000,"channels":1,"durationSeconds":2.0},
                 "segments":[],"processing":{"audioMs":1,"speechToTextMs":1}}
                """.formatted(quote(transcript));
    }

    public static String riskBody(int score, String level, double confidence) {
        return """
                {"riskScore":%d,"riskLevel":"%s","confidence":%s,
                 "indicators":["OTP_REQUEST","BANK_IMPERSONATION"],
                 "indicatorDetails":[],
                 "components":{"modelProbability":0.999912,"modelPoints":69.99,"ruleScore":35.0,
                               "highestSeverity":"HIGH","severityPoints":20.0},
                 "modelVersion":"stub-model-1","rulesetVersion":"stub-rules-1","riskEngineVersion":"stub-risk-1"}
                """.formatted(score, level, confidence);
    }

    private static String quote(String text) {
        return text == null ? "null" : "\"" + text.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
