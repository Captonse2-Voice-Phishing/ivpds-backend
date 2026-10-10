package com.ivpds.analysis;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

/**
 * A local WebSocket server that stands in for the AI service's live endpoint in tests. It is not an AI:
 * each test scripts what it answers, so the backend's relaying, storing and failure handling can be checked.
 */
public final class StubAiLiveServer extends WebSocketServer {

    /** What the stub does at each step of a live session. */
    public interface Script {

        default void onOpen(WebSocket connection) {
            connection.send(READY);
        }

        default void onAudio(WebSocket connection, byte[] frame, int framesSoFar) {
        }

        default void onEnd(WebSocket connection) {
            connection.send(finalEvent("HIGH", 97));
            connection.close(1000);
        }
    }

    public static final String READY = """
            {"type":"ready","seq":0,"sessionId":"stub","apiVersion":"1","sttModel":"stub-whisper",
             "modelVersion":"stub-model-1","rulesetVersion":"stub-rules-1","riskEngineVersion":"stub-risk-1"}""";
    public static final String TRANSCRIPT_EVENT = """
            {"type":"transcript","seq":1,"speaker":"CALLER","start":0.0,"end":2.0,"text":"Anh đọc mã OTP tôi vừa gửi."}""";
    public static final String RISK_EVENT = """
            {"type":"risk","seq":2,"riskScore":97,"riskLevel":"HIGH","confidence":0.87,"indicators":["OTP_REQUEST"],
             "modelProbability":0.999,"newIndicators":["OTP_REQUEST"]}""";
    public static final String ALERT_EVENT = """
            {"type":"alert","seq":3,"riskScore":97,"riskLevel":"HIGH","confidence":0.87,"indicators":["OTP_REQUEST"],
             "modelProbability":0.999,"atSeconds":2.0,"triggeredBy":{"speaker":"CALLER","text":"Anh đọc mã OTP tôi vừa gửi."}}""";

    /** The default script: ready, an alert after the first audio frame, a HIGH result at the end. */
    public static final Script ALERTING = new Script() {
        @Override
        public void onAudio(WebSocket connection, byte[] frame, int framesSoFar) {
            if (framesSoFar == 1) {
                connection.send(TRANSCRIPT_EVENT);
                connection.send(RISK_EVENT);
                connection.send(ALERT_EVENT);
            }
        }
    };

    private final CountDownLatch started = new CountDownLatch(1);
    private final List<byte[]> frames = new CopyOnWriteArrayList<>();
    private final List<String> texts = new CopyOnWriteArrayList<>();
    private volatile String apiKey;
    private volatile String requestId;
    private volatile Script script = ALERTING;

    public StubAiLiveServer() {
        super(new InetSocketAddress("127.0.0.1", 0));
        setReuseAddr(true);
        start();
        try {
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("The stub AI live server did not start");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public String httpBaseUrl() {
        return "http://127.0.0.1:" + getPort();
    }

    /** Back to the default script with nothing recorded. */
    public void reset() {
        script = ALERTING;
        frames.clear();
        texts.clear();
        apiKey = null;
        requestId = null;
    }

    public void script(Script script) {
        this.script = script;
    }

    public List<byte[]> frames() {
        return List.copyOf(frames);
    }

    public List<String> texts() {
        return List.copyOf(texts);
    }

    public String apiKey() {
        return apiKey;
    }

    public String requestId() {
        return requestId;
    }

    public static String finalEvent(String level, int score) {
        return """
                {"type":"final","seq":9,"riskScore":%d,"riskLevel":"%s","confidence":0.87,
                 "indicators":["OTP_REQUEST","BANK_IMPERSONATION"],"modelProbability":0.999912,"endedBy":"CLIENT",
                 "durationSeconds":2.0,"transcript":"Tôi gọi từ ngân hàng. Anh đọc mã OTP tôi vừa gửi.",
                 "turns":[{"speaker":"CALLER","start":0.0,"end":2.0,"text":"Tôi gọi từ ngân hàng. Anh đọc mã OTP tôi vừa gửi."}],
                 "modelVersion":"stub-model-1","rulesetVersion":"stub-rules-1","riskEngineVersion":"stub-risk-1"}"""
                .formatted(score, level);
    }

    public static final String FINAL_WITHOUT_SPEECH = """
            {"type":"final","seq":1,"riskScore":null,"riskLevel":null,"confidence":null,"indicators":[],
             "modelProbability":null,"endedBy":"CLIENT","durationSeconds":2.0,"transcript":"","turns":[],
             "modelVersion":"stub-model-1","rulesetVersion":"stub-rules-1","riskEngineVersion":"stub-risk-1"}""";

    @Override
    public void onStart() {
        started.countDown();
    }

    @Override
    public void onOpen(WebSocket connection, ClientHandshake handshake) {
        apiKey = handshake.getFieldValue("X-API-Key");
        requestId = handshake.getFieldValue("X-Request-Id");
        script.onOpen(connection);
    }

    @Override
    public void onMessage(WebSocket connection, ByteBuffer message) {
        byte[] frame = new byte[message.remaining()];
        message.get(frame);
        frames.add(frame);
        script.onAudio(connection, frame, frames.size());
    }

    @Override
    public void onMessage(WebSocket connection, String message) {
        texts.add(message);
        if (message.contains("\"end\"")) {
            script.onEnd(connection);
        }
    }

    @Override
    public void onClose(WebSocket connection, int code, String reason, boolean remote) {
    }

    @Override
    public void onError(WebSocket connection, Exception error) {
    }
}
