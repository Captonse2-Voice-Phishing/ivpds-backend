package com.ivpds.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

/** Shared steps of the analysis integration tests: sign up, upload a call, ask for and wait for an analysis. */
public abstract class AnalysisTestSupport {

    private static final String PASSWORD = "correct-horse-1";
    private static final Duration PATIENCE = Duration.ofSeconds(20);

    @Autowired
    protected TestRestTemplate rest;
    @Autowired
    protected JdbcTemplate jdbc;

    /** A signed-in user; {@code ANONYMOUS} has no token. */
    public record Session(String accessToken, UUID id, String email, String refreshToken) {
        public static final Session ANONYMOUS = new Session(null, null, null, null);
    }

    protected Session register(String prefix) {
        String email = prefix + "-" + UUID.randomUUID() + "@example.com";
        ResponseEntity<JsonNode> response = rest.postForEntity("/api/v1/auth/register",
                Map.of("email", email, "password", PASSWORD, "fullName", "Test User " + prefix), JsonNode.class);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        return session(response.getBody());
    }

    /** Signs in an existing account; fails the test if the credentials are refused. */
    protected Session login(String email, String password) {
        ResponseEntity<JsonNode> response = loginAttempt(email, password);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        return session(response.getBody());
    }

    protected ResponseEntity<JsonNode> loginAttempt(String email, String password) {
        return rest.postForEntity("/api/v1/auth/login", Map.of("email", email, "password", password), JsonNode.class);
    }

    protected static String password() {
        return PASSWORD;
    }

    private static Session session(JsonNode body) {
        return new Session(body.get("accessToken").asText(), UUID.fromString(body.get("user").get("id").asText()),
                body.get("user").get("email").asText(), body.get("refreshToken").asText());
    }

    /** Sends a JSON request as the given user; {@code body} may be null. */
    protected ResponseEntity<JsonNode> send(Session session, HttpMethod method, String path, Object body) {
        HttpHeaders headers = bearer(session);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange(path, method, new HttpEntity<>(body, headers), JsonNode.class);
    }

    /** Uploads a call that says who called, and returns its id. */
    protected UUID uploadCall(Session session, byte[] audio, String callerNumber) {
        return uploadCall(session, audio, Map.of("callerNumber", callerNumber));
    }

    /** Uploads a call and returns its id. */
    protected UUID uploadCall(Session session, byte[] audio) {
        return uploadCall(session, audio, Map.of());
    }

    private UUID uploadCall(Session session, byte[] audio, Map<String, String> fields) {
        HttpHeaders partHeaders = new HttpHeaders();
        partHeaders.setContentType(MediaType.parseMediaType("audio/wav"));
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("audio", new HttpEntity<>(new ByteArrayResource(audio) {
            @Override
            public String getFilename() {
                return "cuộc gọi.wav";
            }
        }, partHeaders));
        fields.forEach(form::add);
        HttpHeaders headers = bearer(session);
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        ResponseEntity<JsonNode> response = rest.exchange("/api/v1/calls", HttpMethod.POST,
                new HttpEntity<>(form, headers), JsonNode.class);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        return UUID.fromString(response.getBody().get("id").asText());
    }

    protected ResponseEntity<JsonNode> requestAnalysis(Session session, UUID callId) {
        return rest.exchange("/api/v1/calls/" + callId + "/analyses", HttpMethod.POST,
                new HttpEntity<>(bearer(session)), JsonNode.class);
    }

    protected ResponseEntity<JsonNode> latest(Session session, UUID callId) {
        return get(session, "/api/v1/calls/" + callId + "/analyses/latest");
    }

    protected ResponseEntity<JsonNode> get(Session session, String path) {
        return rest.exchange(path, HttpMethod.GET, new HttpEntity<>(bearer(session)), JsonNode.class);
    }

    /** Polls the latest analysis until it is COMPLETED or FAILED, the way a client would. */
    protected JsonNode awaitFinished(Session session, UUID callId) {
        long deadline = System.nanoTime() + PATIENCE.toNanos();
        JsonNode body = null;
        while (System.nanoTime() < deadline) {
            ResponseEntity<JsonNode> response = latest(session, callId);
            if (response.getStatusCode() == HttpStatus.OK) {
                body = response.getBody();
                String status = body.get("status").asText();
                if (status.equals("COMPLETED") || status.equals("FAILED")) {
                    return body;
                }
            }
            sleep(100);
        }
        throw new AssertionError("The analysis did not finish in time; last answer: " + body);
    }

    /** Asks for an analysis, checks it was accepted, and waits for it to finish. */
    protected JsonNode analyse(Session session, UUID callId) {
        ResponseEntity<JsonNode> accepted = requestAnalysis(session, callId);
        assertThat(accepted.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        return awaitFinished(session, callId);
    }

    protected int count(String table, String column, UUID id) {
        return jdbc.queryForObject("select count(*) from " + table + " where " + column + " = ?", Integer.class, id);
    }

    protected static void assertError(ResponseEntity<JsonNode> response, HttpStatus status, String code) {
        assertThat(response.getStatusCode()).isEqualTo(status);
        assertThat(response.getBody().get("code").asText()).isEqualTo(code);
    }

    /** A failed analysis carries an error code and never a risk score, level, confidence or indicators. */
    protected static void assertFailedWithoutRisk(JsonNode analysis, String code) {
        assertThat(analysis.get("status").asText()).isEqualTo("FAILED");
        assertThat(analysis.get("errorCode").asText()).isEqualTo(code);
        assertThat(analysis.get("errorMessage").asText()).isNotBlank();
        assertThat(analysis.get("completedAt").isNull()).isFalse();
        for (String field : new String[] {"riskScore", "riskLevel", "confidence", "indicators"}) {
            assertThat(analysis.get(field).isNull()).as(field).isTrue();
        }
    }

    protected static HttpHeaders bearer(Session session) {
        HttpHeaders headers = new HttpHeaders();
        if (session.accessToken() != null) {
            headers.setBearerAuth(session.accessToken());
        }
        return headers;
    }

    protected static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new AssertionError(e);
        }
    }

    /** A valid WAV file: 16 kHz, mono, 16-bit PCM, a 440 Hz tone of the given length. */
    protected static byte[] wav(int seconds) {
        int sampleRate = 16_000;
        int dataBytes = seconds * sampleRate * 2;
        ByteBuffer buffer = ByteBuffer.allocate(44 + dataBytes).order(ByteOrder.LITTLE_ENDIAN);
        buffer.put("RIFF".getBytes(StandardCharsets.US_ASCII)).putInt(36 + dataBytes)
                .put("WAVE".getBytes(StandardCharsets.US_ASCII))
                .put("fmt ".getBytes(StandardCharsets.US_ASCII)).putInt(16)
                .putShort((short) 1).putShort((short) 1).putInt(sampleRate).putInt(sampleRate * 2)
                .putShort((short) 2).putShort((short) 16)
                .put("data".getBytes(StandardCharsets.US_ASCII)).putInt(dataBytes);
        for (int i = 0; i < seconds * sampleRate; i++) {
            buffer.putShort((short) (Math.sin(2 * Math.PI * 440 * i / sampleRate) * 12_000));
        }
        return buffer.array();
    }
}
