package com.ivpds.analysis;

import static com.ivpds.analysis.StubAiServer.delayed;
import static com.ivpds.analysis.StubAiServer.dropConnection;
import static com.ivpds.analysis.StubAiServer.error;
import static com.ivpds.analysis.StubAiServer.json;
import static com.ivpds.analysis.StubAiServer.raw;
import static com.ivpds.analysis.StubAiServer.riskBody;
import static com.ivpds.analysis.StubAiServer.transcriptionBody;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ivpds.analysis.AiClient.RiskAssessment;
import com.ivpds.analysis.AiClient.Transcription;
import com.ivpds.analysis.StubAiServer.Received;
import java.io.ByteArrayInputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.assertj.core.api.ThrowableAssert.ThrowingCallable;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

/**
 * The HTTP client for the AI service, against a local stub server over real HTTP. These tests check what the
 * backend sends and how it reads every kind of answer; they say nothing about the AI service itself.
 */
class AiClientTest {

    private static final String API_KEY = "client-test-api-key-0123";
    private static final byte[] AUDIO = "RIFF-not-really-audio-but-bytes".getBytes(StandardCharsets.US_ASCII);

    private static final StubAiServer stub = new StubAiServer();
    private final AiClient client = client(stub.baseUrl(), Duration.ofSeconds(5));

    @BeforeEach
    void resetStub() {
        stub.reset();
    }

    @AfterAll
    static void stopStub() {
        stub.close();
    }

    // ----------------------------------------------------------------- success

    @Test
    void transcriptionSendsTheAudioAsMultipartWithTheApiKeyAndRequestId() {
        Transcription result = transcribe(client);

        assertThat(result.transcript()).isEqualTo(StubAiServer.TRANSCRIPT);
        assertThat(result.language()).isEqualTo("vi");
        assertThat(result.sttModel()).isEqualTo("stub-whisper");
        assertThat(result.audio().durationSeconds()).isEqualTo(2.0);

        Received request = stub.received("/v1/transcriptions").get(0);
        assertThat(request.apiKey()).isEqualTo(API_KEY);
        assertThat(request.requestId()).isEqualTo("req-1");
        assertThat(request.contentType()).startsWith("multipart/form-data");
        String body = new String(request.body(), StandardCharsets.ISO_8859_1);
        assertThat(body).contains("name=\"audio\"", "filename=\"call.wav\"", "Content-Type: audio/wav",
                new String(AUDIO, StandardCharsets.ISO_8859_1));
    }

    @Test
    void riskAssessmentSendsTheTranscriptAsJsonAndReadsTheResult() {
        RiskAssessment result = client.assessRisk("Anh đọc mã OTP cho em.", "req-2");

        assertThat(result.riskScore()).isEqualTo(100);
        assertThat(result.riskLevel()).isEqualTo("HIGH");
        assertThat(result.confidence()).isEqualTo(1.0);
        assertThat(result.indicators()).containsExactly("OTP_REQUEST", "BANK_IMPERSONATION");
        assertThat(result.components().modelProbability()).isEqualTo(0.999912);
        assertThat(result.modelVersion()).isEqualTo("stub-model-1");
        assertThat(result.rulesetVersion()).isEqualTo("stub-rules-1");
        assertThat(result.riskEngineVersion()).isEqualTo("stub-risk-1");

        Received request = stub.received("/v1/risk-assessments").get(0);
        assertThat(request.apiKey()).isEqualTo(API_KEY);
        assertThat(request.requestId()).isEqualTo("req-2");
        assertThat(request.contentType()).startsWith("application/json");
        assertThat(new String(request.body(), StandardCharsets.UTF_8)).isEqualTo("{\"text\":\"Anh đọc mã OTP cho em.\"}");
    }

    @Test
    void anEmptyTranscriptIsReturnedAsIsAndLeftToTheCallerToJudge() {
        stub.onTranscription(json(200, transcriptionBody("")));

        assertThat(transcribe(client).transcript()).isEmpty();
    }

    // ----------------------------------------------------- connection failures

    @Test
    void anUnreachableServiceIsReportedAsUnavailable() {
        // Port 9 (discard) is not listening.
        AiClient unreachable = client("http://127.0.0.1:9", Duration.ofSeconds(5));

        assertFails(() -> unreachable.assessRisk("xin chào", "r"), AiServiceException.UNAVAILABLE);
        assertFails(() -> transcribe(unreachable), AiServiceException.UNAVAILABLE);
    }

    @Test
    void aConnectionClosedWithoutAnAnswerIsReportedAsUnavailable() {
        stub.onRisk(dropConnection());

        assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.UNAVAILABLE);
    }

    @Test
    void anAnswerThatTakesLongerThanTheTimeoutIsReportedAsATimeout() {
        AiClient impatient = client(stub.baseUrl(), Duration.ofMillis(300));
        stub.onRisk(delayed(2_000, json(200, riskBody(10, "LOW", 0.9))));
        stub.onTranscription(delayed(2_000, json(200, transcriptionBody("xin chào"))));

        assertFails(() -> impatient.assessRisk("xin chào", "r"), AiServiceException.TIMEOUT);
        assertFails(() -> transcribe(impatient), AiServiceException.TIMEOUT);
    }

    // ------------------------------------------------------------- HTTP errors

    @Test
    void anUnexplainedServerErrorIsReportedAsAServiceError() {
        stub.onRisk(raw(500, "text/plain", "Internal Server Error"));

        assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.ERROR);
    }

    @Test
    void errorCodesOfTheAiServiceAreKeptWhenItSaysWhyItCannotAnswer() {
        stub.onRisk(error(503, "NLP_MODEL_UNAVAILABLE"));
        assertFails(() -> client.assessRisk("xin chào", "r"), "NLP_MODEL_UNAVAILABLE");

        stub.onTranscription(error(503, "STT_UNAVAILABLE"));
        assertFails(() -> transcribe(client), "STT_UNAVAILABLE");

        stub.onTranscription(error(422, "INVALID_AUDIO"));
        assertFails(() -> transcribe(client), "INVALID_AUDIO");

        stub.onTranscription(error(413, "AUDIO_TOO_LARGE"));
        assertFails(() -> transcribe(client), "AUDIO_TOO_LARGE");
    }

    @Test
    void aBare503IsReportedAsUnavailable() {
        stub.onRisk(raw(503, "text/html", "<html>Bad Gateway</html>"));

        assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.UNAVAILABLE);
    }

    @Test
    void aRejectedApiKeyIsReportedAsAnAuthenticationFailure() {
        stub.onRisk(error(401, "UNAUTHORIZED"));

        assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.AUTH_FAILED);
    }

    @Test
    void anUnexpectedClientErrorIsReportedAsARejectedRequest() {
        stub.onRisk(error(400, "VALIDATION_FAILED"));

        assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.REQUEST_REJECTED);
    }

    @Test
    void anErrorCodeThatDoesNotLookLikeACodeIsNotTrusted() {
        stub.onRisk(json(503, "{\"code\":\"<script>alert(1)</script>\"}"));

        assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.UNAVAILABLE);
    }

    // ------------------------------------------------------- invalid responses

    @Test
    void aSuccessfulAnswerThatIsNotJsonIsAnInvalidResponse() {
        stub.onRisk(raw(200, "application/json", "this is not json"));
        assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.INVALID_RESPONSE);

        stub.onTranscription(raw(200, "text/html", "<html>hello</html>"));
        assertFails(() -> transcribe(client), AiServiceException.INVALID_RESPONSE);
    }

    @Test
    void aTranscriptionWithoutATranscriptIsAnInvalidResponse() {
        stub.onTranscription(json(200, "{\"language\":\"vi\"}"));
        assertFails(() -> transcribe(client), AiServiceException.INVALID_RESPONSE);

        stub.onTranscription(json(200, transcriptionBody(null)));
        assertFails(() -> transcribe(client), AiServiceException.INVALID_RESPONSE);
    }

    @Test
    void aRiskResultWithMissingOrOutOfRangeValuesIsAnInvalidResponseAndNeverUsed() {
        for (String body : new String[] {
                "{}",
                "{\"riskScore\":50,\"riskLevel\":\"MEDIUM\",\"confidence\":0.5}",
                "{\"riskLevel\":\"MEDIUM\",\"confidence\":0.5,\"indicators\":[]}",
                riskBody(101, "HIGH", 0.9),
                riskBody(-1, "LOW", 0.9),
                riskBody(50, "CRITICAL", 0.9),
                riskBody(50, "MEDIUM", 1.5),
                riskBody(50, "MEDIUM", -0.1),
                "{\"riskScore\":50,\"riskLevel\":\"MEDIUM\",\"confidence\":0.5,\"indicators\":[\"\"]}",
                "{\"riskScore\":50,\"riskLevel\":\"MEDIUM\",\"confidence\":0.5,\"indicators\":[],"
                        + "\"components\":{\"modelProbability\":7}}",
                "{\"riskScore\":\"high\",\"riskLevel\":\"MEDIUM\",\"confidence\":0.5,\"indicators\":[]}",
        }) {
            stub.onRisk(json(200, body));

            assertFails(() -> client.assessRisk("xin chào", "r"), AiServiceException.INVALID_RESPONSE);
        }
    }

    // ----------------------------------------------------------------- helpers

    private static AiClient client(String baseUrl, Duration readTimeout) {
        AiProperties properties = new AiProperties(URI.create(baseUrl), API_KEY, Duration.ofSeconds(2), readTimeout,
                readTimeout, Duration.ofSeconds(5));
        return new AiClient(RestClient.builder(), properties);
    }

    private static Transcription transcribe(AiClient client) {
        return client.transcribe(new ByteArrayInputStream(AUDIO), AUDIO.length, "call.wav", "audio/wav", "req-1");
    }

    private static void assertFails(ThrowingCallable call, String code) {
        assertThatThrownBy(call)
                .isInstanceOfSatisfying(AiServiceException.class, e -> assertThat(e.getCode()).isEqualTo(code));
    }
}
