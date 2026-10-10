package com.ivpds.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.ivpds.analysis.StubAiLiveServer.Script;
import java.math.BigDecimal;
import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.java_websocket.WebSocket;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

/**
 * Live calls over a real WebSocket against the real application, a real PostgreSQL and a real MinIO.
 * Only the AI service is replaced, by a local WebSocket stub with scripted answers. The real AI service's
 * live endpoint is exercised separately.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({TestcontainersConfig.class, MinioConfig.class})
class LiveCallIntegrationTest extends AnalysisTestSupport {

    private static final StubAiLiveServer ai = new StubAiLiveServer();
    private static final ObjectMapper json = new ObjectMapper();

    @LocalServerPort
    private int port;
    @Autowired
    private LiveCallTickets tickets;

    @DynamicPropertySource
    static void aiProperties(DynamicPropertyRegistry registry) {
        registry.add("ivpds.ai.base-url", ai::httpBaseUrl);
        registry.add("ivpds.ai.live-finish-timeout", () -> "2s");
    }

    @BeforeEach
    void resetStub() {
        ai.reset();
    }

    @AfterAll
    static void stopStub() throws Exception {
        ai.stop(1000);
    }

    // ----------------------------------------------------------------- opening

    @Test
    void openingALiveCallNeedsASignedInUserAndReturnsWhatTheClientNeedsToStream() {
        assertThat(open(Session.ANONYMOUS, null).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertError(open(register("badnumber"), "abc"), HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");

        Session user = register("open");
        ResponseEntity<JsonNode> response = open(user, "090 123 4567");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        JsonNode body = response.getBody();
        assertThat(body.get("streamPath").asText()).isEqualTo("/api/v1/live-calls/stream");
        assertThat(body.get("ticket").asText()).hasSizeGreaterThan(30);
        assertThat(body.get("ticketExpiresInSeconds").asInt()).isEqualTo(60);
        assertThat(body.get("audioFormat").get("encoding").asText()).isEqualTo("pcm_s16le");
        assertThat(body.get("audioFormat").get("sampleRate").asInt()).isEqualTo(16_000);
        assertThat(body.get("audioFormat").get("speakerPrefix").get("0").asText()).isEqualTo("CALLER");
        // The call exists at once, as a LIVE call whose analysis is in progress.
        UUID callId = UUID.fromString(body.get("callId").asText());
        JsonNode call = get(user, "/api/v1/calls/" + callId).getBody();
        assertThat(call.get("source").asText()).isEqualTo("LIVE");
        assertThat(call.get("callerNumber").asText()).isEqualTo("+84901234567");
        assertThat(call.get("audio").isNull()).isTrue();
        assertThat(latest(user, callId).getBody().get("status").asText()).isEqualTo("PROCESSING");
    }

    @Test
    void theStreamOnlyOpensWithAValidTicketAndATicketWorksOnce() throws Exception {
        Session user = register("ticket");
        String ticket = open(user, null).getBody().get("ticket").asText();

        assertThatThrownBy(() -> connect(null)).hasMessageContaining("401");
        assertThatThrownBy(() -> connect("not-a-ticket")).hasMessageContaining("401");
        // A valid access token is not a ticket.
        assertThatThrownBy(() -> connect(user.accessToken())).hasMessageContaining("401");

        try (Client first = connect(ticket)) {
            assertThat(first.next().get("type").asText()).isEqualTo("ready");
            assertThatThrownBy(() -> connect(ticket)).hasMessageContaining("401");
        }
    }

    @Test
    void uploadingAFileCannotClaimToBeALiveCall() {
        Session user = register("fake-live");
        HttpHeaders headers = bearer(user);
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        org.springframework.util.LinkedMultiValueMap<String, Object> form = new org.springframework.util.LinkedMultiValueMap<>();
        form.add("audio", new org.springframework.core.io.ByteArrayResource(wav(1)) {
            @Override
            public String getFilename() {
                return "a.wav";
            }
        });
        form.add("source", "LIVE");

        assertError(rest.exchange("/api/v1/calls", HttpMethod.POST, new HttpEntity<>(form, headers), JsonNode.class),
                HttpStatus.BAD_REQUEST, "INVALID_CALL_SOURCE");
    }

    // ----------------------------------------------------------------- success

    @Test
    void aLiveCallIsRelayedToTheAiServiceAlertsDuringTheCallAndIsStoredAtTheEnd() throws Exception {
        Session user = register("live");
        JsonNode opened = open(user, null).getBody();
        UUID callId = UUID.fromString(opened.get("callId").asText());
        UUID analysisId = UUID.fromString(opened.get("analysisId").asText());
        byte[] caller = frame(0, tone(1.0));
        byte[] callee = frame(1, tone(0.5));

        try (Client client = connect(opened.get("ticket").asText())) {
            assertThat(client.next().get("type").asText()).isEqualTo("ready");
            client.send(caller);
            // The alert reaches the app while the call is still going on.
            assertThat(List.of(client.next().get("type").asText(), client.next().get("type").asText()))
                    .containsExactly("transcript", "risk");
            JsonNode alert = client.next();
            assertThat(alert.get("type").asText()).isEqualTo("alert");
            assertThat(alert.get("riskLevel").asText()).isEqualTo("HIGH");
            assertThat(alert.get("triggeredBy").get("text").asText()).isEqualTo("Anh đọc mã OTP tôi vừa gửi.");
            assertThat(latest(user, callId).getBody().get("status").asText()).isEqualTo("PROCESSING");

            client.send(callee);
            client.sendText("{\"type\":\"end\"}");
            JsonNode last = client.next();
            assertThat(last.get("type").asText()).isEqualTo("final");
            assertThat(last.get("riskLevel").asText()).isEqualTo("HIGH");
            assertThat(client.closed().get(5, TimeUnit.SECONDS).getCode()).isEqualTo(1000);
        }

        // The AI service got the audio exactly as sent, the API key, and the analysis id as trace id.
        assertThat(ai.frames()).containsExactly(caller, callee);
        assertThat(ai.apiKey()).isEqualTo("test-ai-api-key-0123456789");
        assertThat(ai.requestId()).isEqualTo(analysisId.toString());

        // The result is stored like any other analysis.
        JsonNode done = awaitFinished(user, callId);
        assertThat(done.get("status").asText()).isEqualTo("COMPLETED");
        assertThat(done.get("transcript").asText()).isEqualTo("Tôi gọi từ ngân hàng. Anh đọc mã OTP tôi vừa gửi.");
        assertThat(done.get("riskScore").asInt()).isEqualTo(97);
        assertThat(done.get("riskLevel").asText()).isEqualTo("HIGH");
        assertThat(done.get("indicators")).extracting(JsonNode::asText)
                .containsExactly("BANK_IMPERSONATION", "OTP_REQUEST");
        assertThat(done.get("details").get("sttModel").asText()).isEqualTo("stub-whisper");
        assertThat(done.get("details").get("nlpModelVersion").asText()).isEqualTo("stub-model-1");

        // The recording is in storage as a stereo WAV: caller left, callee right, the shorter side padded.
        JsonNode audio = get(user, "/api/v1/calls/" + callId).getBody().get("audio");
        assertThat(audio.get("contentType").asText()).isEqualTo("audio/wav");
        assertThat(audio.get("durationSeconds").decimalValue()).isEqualByComparingTo("1.000");
        assertThat(audio.get("sizeBytes").asLong()).isEqualTo(44 + 16_000 * 4);
        byte[] stored = rest.exchange("/api/v1/calls/" + callId + "/audio", HttpMethod.GET,
                new HttpEntity<>(bearer(user)), byte[].class).getBody();
        assertThat(stored).hasSize(44 + 16_000 * 4);
        ByteBuffer samples = ByteBuffer.wrap(stored, 44, stored.length - 44).order(ByteOrder.LITTLE_ENDIAN);
        ByteBuffer left = ByteBuffer.wrap(caller, 1, caller.length - 1).order(ByteOrder.LITTLE_ENDIAN);
        ByteBuffer right = ByteBuffer.wrap(callee, 1, callee.length - 1).order(ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i < 16_000; i++) {
            assertThat(samples.getShort()).as("left %d", i).isEqualTo(left.getShort());
            assertThat(samples.getShort()).as("right %d", i).isEqualTo(i < 8_000 ? right.getShort() : (short) 0);
        }
    }

    @Test
    void hangingUpWithoutSayingEndStillFinishesAndStoresTheCall() throws Exception {
        Session user = register("hangup");
        JsonNode opened = open(user, null).getBody();
        UUID callId = UUID.fromString(opened.get("callId").asText());

        try (Client client = connect(opened.get("ticket").asText())) {
            client.next();
            client.send(frame(0, tone(0.5)));
            client.next();
        }

        JsonNode done = awaitFinished(user, callId);
        assertThat(done.get("status").asText()).isEqualTo("COMPLETED");
        assertThat(done.get("riskLevel").asText()).isEqualTo("HIGH");
        assertThat(ai.texts()).anyMatch(text -> text.contains("\"end\""));
    }

    // ---------------------------------------------------------------- failures

    @Test
    void aCallInWhichNothingWasRecognisedFailsWithoutARiskLevelButKeepsItsRecording() throws Exception {
        ai.script(new Script() {
            @Override
            public void onEnd(WebSocket connection) {
                connection.send(StubAiLiveServer.FINAL_WITHOUT_SPEECH);
                connection.close(1000);
            }
        });
        Session user = register("nospeech");
        JsonNode opened = open(user, null).getBody();
        UUID callId = UUID.fromString(opened.get("callId").asText());

        try (Client client = connect(opened.get("ticket").asText())) {
            client.next();
            client.send(frame(1, tone(0.5)));
            client.sendText("{\"type\":\"end\"}");
            assertThat(client.next().get("type").asText()).isEqualTo("final");
        }

        assertFailedWithoutRisk(awaitFinished(user, callId), "NO_SPEECH_DETECTED");
        assertThat(get(user, "/api/v1/calls/" + callId).getBody().get("audio").get("durationSeconds").decimalValue())
                .isEqualByComparingTo("0.5");
    }

    @Test
    void failuresOfTheAiServiceDuringACallFailTheAnalysisWithTheirCodeAndTellTheApp() throws Exception {
        Map<String, Script> failures = Map.of(
                "LIVE_SESSION_OVERLOADED", new Script() {
                    @Override
                    public void onAudio(WebSocket connection, byte[] frame, int framesSoFar) {
                        connection.send("{\"type\":\"transcript\",\"seq\":1,\"speaker\":\"CALLER\",\"start\":0,\"end\":1,"
                                + "\"text\":\"Tôi gọi từ ngân hàng.\"}");
                        connection.send("{\"type\":\"error\",\"code\":\"LIVE_SESSION_OVERLOADED\",\"message\":\"x\"}");
                        connection.close(4503);
                    }
                },
                "STT_UNAVAILABLE", new Script() {
                    @Override
                    public void onOpen(WebSocket connection) {
                        connection.send("{\"type\":\"error\",\"code\":\"STT_UNAVAILABLE\",\"message\":\"x\"}");
                        connection.close(4503);
                    }
                },
                "AI_SERVICE_UNAVAILABLE", new Script() {
                    @Override
                    public void onAudio(WebSocket connection, byte[] frame, int framesSoFar) {
                        connection.closeConnection(1006, "crash");
                    }
                },
                "AI_SERVICE_TIMEOUT", new Script() {
                    @Override
                    public void onEnd(WebSocket connection) {
                        // never answers
                    }
                },
                "AI_INVALID_RESPONSE", new Script() {
                    @Override
                    public void onEnd(WebSocket connection) {
                        connection.send(StubAiLiveServer.finalEvent("HIGH", 250));
                        connection.close(1000);
                    }
                });

        for (Map.Entry<String, Script> failure : failures.entrySet()) {
            String code = failure.getKey();
            ai.reset();
            ai.script(failure.getValue());
            Session user = register("fail");
            JsonNode opened = open(user, null).getBody();
            UUID callId = UUID.fromString(opened.get("callId").asText());

            List<JsonNode> events = new ArrayList<>();
            try (Client client = connect(opened.get("ticket").asText())) {
                client.send(frame(0, tone(0.5)));
                client.sendText("{\"type\":\"end\"}");
                JsonNode event;
                while ((event = client.poll(Duration.ofSeconds(6))) != null) {
                    events.add(event);
                }
            }

            JsonNode failed = awaitFinished(user, callId);
            assertFailedWithoutRisk(failed, code);
            assertThat(events).as(code).isNotEmpty();
            JsonNode last = events.get(events.size() - 1);
            assertThat(last.get("type").asText()).as(code).isEqualTo("error");
            assertThat(last.get("code").asText()).as(code).isEqualTo(code);
            assertThat(count("risk_results", "analysis_id", UUID.fromString(failed.get("id").asText()))).isZero();
            if (code.equals("LIVE_SESSION_OVERLOADED")) {
                // What was recognised before the failure is real and is kept.
                assertThat(failed.get("transcript").asText()).isEqualTo("Tôi gọi từ ngân hàng.");
            }
            // After a failed live call the stored recording can still be analysed as a file.
            assertThat(jdbc.queryForObject("select duration_seconds from audio_files where call_record_id = ?",
                    BigDecimal.class, callId)).as(code).isEqualByComparingTo("0.5");
        }
    }

    @Test
    void anAudioFrameThatBreaksTheFormatEndsTheCallWithAReasonAndKeepsWhatCameBefore() throws Exception {
        Session user = register("badframe");
        JsonNode opened = open(user, null).getBody();
        UUID callId = UUID.fromString(opened.get("callId").asText());

        try (Client client = connect(opened.get("ticket").asText())) {
            client.next();
            client.send(frame(0, tone(0.5)));
            client.send(new byte[] {7, 1, 2});
            List<String> types = new ArrayList<>();
            JsonNode event;
            while ((event = client.poll(Duration.ofSeconds(5))) != null) {
                types.add(event.get("type").asText() + (event.has("code") ? ":" + event.get("code").asText() : ""));
            }
            assertThat(types).contains("error:INVALID_AUDIO_FRAME").endsWith("final");
        }

        assertThat(awaitFinished(user, callId).get("status").asText()).isEqualTo("COMPLETED");
        // The broken frame was not passed on.
        assertThat(ai.frames()).hasSize(1);
    }

    @Test
    void aLiveCallThatWasOpenedButNeverStreamedIsFailedWhenItsTicketExpires() {
        LiveCallTickets shortLived = new LiveCallTickets(Duration.ofMillis(50));
        UUID callId = UUID.randomUUID();
        String ticket = shortLived.issue(callId, UUID.randomUUID(), UUID.randomUUID());
        sleep(120);

        assertThat(shortLived.consume(ticket)).isEmpty();
        String second = shortLived.issue(callId, UUID.randomUUID(), UUID.randomUUID());
        sleep(120);
        assertThat(shortLived.removeExpired()).extracting(LiveCallTickets.Ticket::callId).containsExactly(callId);
        assertThat(shortLived.removeExpired()).isEmpty();
        assertThat(shortLived.consume(second)).isEmpty();
        // The application's own tickets live for a minute and are untouched by this.
        assertThat(tickets.ttl()).isEqualTo(Duration.ofSeconds(60));
    }

    // ----------------------------------------------------------------- helpers

    private ResponseEntity<JsonNode> open(Session session, String callerNumber) {
        HttpHeaders headers = bearer(session);
        headers.setContentType(MediaType.APPLICATION_JSON);
        Map<String, String> body = callerNumber == null ? Map.of() : Map.of("callerNumber", callerNumber);
        return rest.exchange("/api/v1/live-calls", HttpMethod.POST, new HttpEntity<>(body, headers), JsonNode.class);
    }

    private Client connect(String ticket) throws Exception {
        Client client = new Client();
        String query = ticket == null ? "" : "?ticket=" + ticket;
        URI uri = URI.create("ws://127.0.0.1:" + port + "/api/v1/live-calls/stream" + query);
        try {
            client.session = new StandardWebSocketClient().execute(client, uri.toString()).get(10, TimeUnit.SECONDS);
        } catch (java.util.concurrent.ExecutionException e) {
            throw new IllegalStateException(String.valueOf(e.getCause()), e.getCause());
        }
        return client;
    }

    /** One byte saying who speaks, then PCM16 samples. */
    private static byte[] frame(int speaker, byte[] pcm) {
        byte[] frame = new byte[pcm.length + 1];
        frame[0] = (byte) speaker;
        System.arraycopy(pcm, 0, frame, 1, pcm.length);
        return frame;
    }

    private static byte[] tone(double seconds) {
        int samples = (int) (seconds * 16_000);
        ByteBuffer buffer = ByteBuffer.allocate(samples * 2).order(ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i < samples; i++) {
            buffer.putShort((short) (Math.sin(2 * Math.PI * 300 * i / 16_000.0) * 8_000));
        }
        return buffer.array();
    }

    /** The app's side of the stream. */
    private static final class Client extends TextWebSocketHandler implements AutoCloseable {

        private final BlockingQueue<JsonNode> events = new LinkedBlockingQueue<>();
        private final CompletableFuture<CloseStatus> closed = new CompletableFuture<>();
        private WebSocketSession session;

        @Override
        protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
            events.add(json.readTree(message.getPayload()));
        }

        @Override
        public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
            closed.complete(status);
        }

        JsonNode next() throws InterruptedException {
            JsonNode event = poll(Duration.ofSeconds(10));
            assertThat(event).as("an event from the backend").isNotNull();
            return event;
        }

        JsonNode poll(Duration patience) throws InterruptedException {
            return events.poll(patience.toMillis(), TimeUnit.MILLISECONDS);
        }

        void send(byte[] frame) throws Exception {
            session.sendMessage(new BinaryMessage(frame));
        }

        void sendText(String text) throws Exception {
            session.sendMessage(new TextMessage(text));
        }

        CompletableFuture<CloseStatus> closed() {
            return closed;
        }

        @Override
        public void close() throws Exception {
            if (session != null && session.isOpen()) {
                session.close();
            }
        }
    }
}
