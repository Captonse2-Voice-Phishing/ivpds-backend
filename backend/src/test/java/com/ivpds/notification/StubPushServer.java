package com.ivpds.notification;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;

/**
 * A local HTTP server that stands in for the Expo Push Service in tests. It records what the backend sends and
 * answers what the test tells it to. It delivers nothing to any device: whether a real phone receives a
 * notification can only be checked with a real Expo project and a real device.
 */
public final class StubPushServer implements AutoCloseable {

    /** One request the stub received. */
    public record Received(String authorization, String contentType, String body) {
    }

    private final HttpServer server;
    private final List<Received> received = new CopyOnWriteArrayList<>();
    private volatile int status;
    private volatile String answer;

    public StubPushServer() {
        try {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        server.setExecutor(Executors.newCachedThreadPool());
        server.createContext("/push/send", exchange -> {
            try (exchange) {
                String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                received.add(new Received(exchange.getRequestHeaders().getFirst("Authorization"),
                        exchange.getRequestHeaders().getFirst("Content-Type"), body));
                byte[] bytes = answer.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(status, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        reset();
    }

    public String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort() + "/push/send";
    }

    /** Back to accepting every message, with nothing recorded. */
    public void reset() {
        received.clear();
        answer(200, "{\"data\":[]}");
    }

    public void answer(int status, String body) {
        this.status = status;
        this.answer = body;
    }

    public List<Received> received() {
        return List.copyOf(received);
    }

    @Override
    public void close() {
        server.stop(0);
    }

    /** The ticket Expo returns for a message it accepted. */
    public static String ok() {
        return "{\"status\":\"ok\",\"id\":\"ticket-1\"}";
    }

    /** The ticket Expo returns for a message it refused. */
    public static String refused(String error) {
        return "{\"status\":\"error\",\"message\":\"stub\",\"details\":{\"error\":\"" + error + "\"}}";
    }
}
