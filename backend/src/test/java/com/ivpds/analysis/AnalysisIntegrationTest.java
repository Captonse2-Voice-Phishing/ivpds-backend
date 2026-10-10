package com.ivpds.analysis;

import static com.ivpds.analysis.StubAiServer.delayed;
import static com.ivpds.analysis.StubAiServer.dropConnection;
import static com.ivpds.analysis.StubAiServer.error;
import static com.ivpds.analysis.StubAiServer.json;
import static com.ivpds.analysis.StubAiServer.raw;
import static com.ivpds.analysis.StubAiServer.riskBody;
import static com.ivpds.analysis.StubAiServer.transcriptionBody;
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.ivpds.analysis.StubAiServer.Behaviour;
import com.ivpds.analysis.StubAiServer.Received;
import com.ivpds.audio.StorageProperties;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import software.amazon.awssdk.services.s3.S3Client;

/**
 * The analysis flow over real HTTP against the real application, a real PostgreSQL and a real MinIO.
 * Only the AI service is replaced, by a local stub that answers what each test tells it to, so every
 * failure of the AI service can be produced on demand. The real AI service is exercised separately.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({TestcontainersConfig.class, MinioConfig.class})
class AnalysisIntegrationTest extends AnalysisTestSupport {

    private static final StubAiServer ai = new StubAiServer();

    @Autowired
    private AnalysisService analysisService;
    @Autowired
    private S3Client s3;
    @Autowired
    private StorageProperties storage;

    @DynamicPropertySource
    static void aiProperties(DynamicPropertyRegistry registry) {
        registry.add("ivpds.ai.base-url", ai::baseUrl);
        registry.add("ivpds.ai.transcription-timeout", () -> "5s");
        registry.add("ivpds.ai.risk-timeout", () -> "1s");
    }

    @BeforeEach
    void resetStub() {
        ai.reset();
    }

    @AfterAll
    static void stopStub() {
        ai.close();
    }

    // ----------------------------------------------------------------- success

    @Test
    void anAnalysisSendsTheStoredAudioToTheAiServiceAndStoresWhatItAnswers() {
        Session user = register("analysis");
        byte[] audio = wav(2);
        UUID callId = uploadCall(user, audio);

        ResponseEntity<JsonNode> accepted = requestAnalysis(user, callId);

        assertThat(accepted.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(accepted.getBody().get("status").asText()).isIn("PENDING", "PROCESSING", "COMPLETED");
        assertThat(accepted.getBody().get("callId").asText()).isEqualTo(callId.toString());

        JsonNode done = awaitFinished(user, callId);
        UUID analysisId = UUID.fromString(done.get("id").asText());
        assertThat(done.get("status").asText()).isEqualTo("COMPLETED");
        assertThat(done.get("errorCode").isNull()).isTrue();
        // The README contract fields, with exactly what the AI service answered.
        assertThat(done.get("transcript").asText()).isEqualTo(StubAiServer.TRANSCRIPT);
        assertThat(done.get("riskScore").asInt()).isEqualTo(100);
        assertThat(done.get("riskLevel").asText()).isEqualTo("HIGH");
        assertThat(done.get("confidence").decimalValue()).isEqualByComparingTo("1");
        assertThat(done.get("indicators")).extracting(JsonNode::asText)
                .containsExactly("BANK_IMPERSONATION", "OTP_REQUEST");
        assertThat(done.get("language").asText()).isEqualTo("vi");
        assertThat(done.get("details").get("sttModel").asText()).isEqualTo("stub-whisper");
        assertThat(done.get("details").get("modelProbability").decimalValue()).isEqualByComparingTo("0.999912");
        assertThat(done.get("details").get("nlpModelVersion").asText()).isEqualTo("stub-model-1");
        assertThat(done.get("details").get("rulesetVersion").asText()).isEqualTo("stub-rules-1");
        assertThat(done.get("details").get("riskEngineVersion").asText()).isEqualTo("stub-risk-1");
        assertThat(done.get("startedAt").isNull()).isFalse();
        assertThat(done.get("completedAt").isNull()).isFalse();

        // What the AI service received: the stored audio byte for byte, the API key, one id for both calls.
        Received transcription = ai.received("/v1/transcriptions").get(0);
        assertThat(new String(transcription.body(), StandardCharsets.ISO_8859_1))
                .contains(new String(audio, StandardCharsets.ISO_8859_1));
        assertThat(transcription.apiKey()).isEqualTo("test-ai-api-key-0123456789");
        Received risk = ai.received("/v1/risk-assessments").get(0);
        assertThat(new String(risk.body(), StandardCharsets.UTF_8)).contains(StubAiServer.TRANSCRIPT);
        assertThat(risk.requestId()).isEqualTo(transcription.requestId()).isEqualTo(analysisId.toString());

        // What is in the database.
        Map<String, Object> row = jdbc.queryForMap("""
                select r.risk_score, r.risk_level, r.confidence, r.model_probability, t.content, t.stt_model
                  from risk_results r join transcripts t on t.analysis_id = r.analysis_id
                 where r.analysis_id = ?""", analysisId);
        assertThat(((Number) row.get("risk_score")).intValue()).isEqualTo(100);
        assertThat(row.get("risk_level")).isEqualTo("HIGH");
        assertThat((BigDecimal) row.get("model_probability")).isEqualByComparingTo("0.999912");
        assertThat(row.get("content")).isEqualTo(StubAiServer.TRANSCRIPT);
        assertThat(jdbc.queryForList("""
                select i.indicator_code from risk_indicators i join risk_results r on r.id = i.risk_result_id
                 where r.analysis_id = ? order by 1""", String.class, analysisId))
                .containsExactly("BANK_IMPERSONATION", "OTP_REQUEST");
        // The duration measured by the AI service is saved on the audio file.
        assertThat(jdbc.queryForObject("select duration_seconds from audio_files where call_record_id = ?",
                BigDecimal.class, callId)).isEqualByComparingTo("2");
        assertThat(get(user, "/api/v1/calls/" + callId).getBody().get("audio").get("durationSeconds").decimalValue())
                .isEqualByComparingTo("2");
    }

    @Test
    void aLowRiskAnswerIsStoredAsLowWithAnEmptyIndicatorList() {
        ai.onRisk(json(200, """
                {"riskScore":0,"riskLevel":"LOW","confidence":1.0,"indicators":[],
                 "components":{"modelProbability":0.0},"modelVersion":"m","rulesetVersion":"r","riskEngineVersion":"e"}
                """));
        Session user = register("low");

        JsonNode done = analyse(user, uploadCall(user, wav(1)));

        assertThat(done.get("status").asText()).isEqualTo("COMPLETED");
        assertThat(done.get("riskScore").asInt()).isZero();
        assertThat(done.get("riskLevel").asText()).isEqualTo("LOW");
        assertThat(done.get("indicators").isArray()).isTrue();
        assertThat(done.get("indicators")).isEmpty();
    }

    // ----------------------------------------------------------- authorization

    @Test
    void analysesAreOnlyForTheSignedInOwnerOfTheCall() {
        Session owner = register("owner");
        Session other = register("other");
        UUID callId = uploadCall(owner, wav(1));
        analyse(owner, callId);

        assertThat(requestAnalysis(Session.ANONYMOUS, callId).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(latest(Session.ANONYMOUS, callId).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        // Someone else's call looks like it does not exist.
        assertError(requestAnalysis(other, callId), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(latest(other, callId), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(get(other, "/api/v1/calls/" + callId + "/analyses"), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(requestAnalysis(owner, UUID.randomUUID()), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
    }

    @Test
    void aCallThatWasNeverAnalysedHasNoLatestAnalysisAndUploadingDoesNotStartOneWhenAutoStartIsOff() {
        Session user = register("none");
        UUID callId = uploadCall(user, wav(1));

        assertError(latest(user, callId), HttpStatus.NOT_FOUND, "ANALYSIS_NOT_FOUND");
        assertThat(get(user, "/api/v1/calls/" + callId + "/analyses").getBody()).isEmpty();
        assertThat(ai.received()).isEmpty();
    }

    // ------------------------------------------------- AI service failures

    @Test
    void failuresOfSpeechToTextFailTheAnalysisWithTheirCodeAndNothingIsInvented() {
        Session user = register("stt");
        Map<String, Behaviour> failures = Map.of(
                "STT_UNAVAILABLE", error(503, "STT_UNAVAILABLE"),
                "INVALID_AUDIO", error(422, "INVALID_AUDIO"),
                "AUDIO_TOO_LONG", error(422, "AUDIO_TOO_LONG"),
                "AI_SERVICE_UNAVAILABLE", dropConnection(),
                "AI_SERVICE_ERROR", raw(500, "text/plain", "boom"),
                "AI_SERVICE_AUTH_FAILED", error(401, "UNAUTHORIZED"),
                "AI_INVALID_RESPONSE", raw(200, "application/json", "not json"));

        failures.forEach((code, behaviour) -> {
            ai.reset();
            ai.onTranscription(behaviour);
            UUID callId = uploadCall(user, wav(1));

            JsonNode failed = analyse(user, callId);

            assertFailedWithoutRisk(failed, code);
            assertThat(failed.get("transcript").isNull()).as(code).isTrue();
            UUID analysisId = UUID.fromString(failed.get("id").asText());
            assertThat(count("transcripts", "analysis_id", analysisId)).as(code).isZero();
            assertThat(count("risk_results", "analysis_id", analysisId)).as(code).isZero();
            // The risk engine is never asked about a transcript that does not exist.
            assertThat(ai.received("/v1/risk-assessments")).as(code).isEmpty();
        });
    }

    @Test
    void failuresOfTheRiskEngineFailTheAnalysisButKeepTheTranscript() {
        Session user = register("risk");
        Map<String, Behaviour> failures = Map.of(
                "NLP_MODEL_UNAVAILABLE", error(503, "NLP_MODEL_UNAVAILABLE"),
                "AI_SERVICE_ERROR", raw(500, "text/plain", "boom"),
                "AI_SERVICE_UNAVAILABLE", dropConnection(),
                "AI_SERVICE_TIMEOUT", delayed(3_000, json(200, riskBody(90, "HIGH", 0.9))),
                "AI_INVALID_RESPONSE", json(200, riskBody(250, "HIGH", 0.9)));

        failures.forEach((code, behaviour) -> {
            ai.reset();
            ai.onRisk(behaviour);
            UUID callId = uploadCall(user, wav(1));

            JsonNode failed = analyse(user, callId);

            assertFailedWithoutRisk(failed, code);
            // The transcript is real, so it is kept and shown.
            assertThat(failed.get("transcript").asText()).as(code).isEqualTo(StubAiServer.TRANSCRIPT);
            UUID analysisId = UUID.fromString(failed.get("id").asText());
            assertThat(count("transcripts", "analysis_id", analysisId)).as(code).isOne();
            assertThat(count("risk_results", "analysis_id", analysisId)).as(code).isZero();
        });
    }

    @Test
    void audioWithoutSpeechFailsWithoutAskingForARiskScore() {
        ai.onTranscription(json(200, transcriptionBody("   ")));
        Session user = register("silence");

        JsonNode failed = analyse(user, uploadCall(user, wav(1)));

        assertFailedWithoutRisk(failed, "NO_SPEECH_DETECTED");
        assertThat(failed.get("transcript").isNull()).isTrue();
        assertThat(ai.received("/v1/risk-assessments")).isEmpty();
        // The measured duration is real even without speech, so it is kept.
        assertThat(jdbc.queryForObject("select duration_seconds from audio_files where call_record_id = ?",
                BigDecimal.class, UUID.fromString(failed.get("callId").asText()))).isEqualByComparingTo("2");
    }

    @Test
    void audioThatIsGoneFromStorageFailsWithoutCallingTheAiService() {
        Session user = register("missing");
        UUID callId = uploadCall(user, wav(1));
        String key = jdbc.queryForObject("select object_key from audio_files where call_record_id = ?", String.class,
                callId);
        s3.deleteObject(b -> b.bucket(storage.bucket()).key(key));

        JsonNode failed = analyse(user, callId);

        assertFailedWithoutRisk(failed, "AUDIO_OBJECT_MISSING");
        assertThat(ai.received()).isEmpty();
    }

    // ------------------------------------------------------------ concurrency

    @Test
    void aCallCannotBeAnalysedTwiceAtTheSameTimeButCanBeAnalysedAgainAfterwards() throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ai.onTranscription((exchange, body) -> {
            entered.countDown();
            try {
                release.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            error(503, "STT_UNAVAILABLE").handle(exchange, body);
        });
        Session user = register("twice");
        UUID callId = uploadCall(user, wav(1));

        assertThat(requestAnalysis(user, callId).getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(entered.await(10, TimeUnit.SECONDS)).isTrue();
        assertThat(latest(user, callId).getBody().get("status").asText()).isEqualTo("PROCESSING");
        assertError(requestAnalysis(user, callId), HttpStatus.CONFLICT, "ANALYSIS_IN_PROGRESS");
        release.countDown();
        assertFailedWithoutRisk(awaitFinished(user, callId), "STT_UNAVAILABLE");

        // After a failure the user can ask again; the earlier attempt stays in the history.
        ai.reset();
        JsonNode second = analyse(user, callId);
        assertThat(second.get("status").asText()).isEqualTo("COMPLETED");

        JsonNode history = get(user, "/api/v1/calls/" + callId + "/analyses").getBody();
        assertThat(history).hasSize(2);
        assertThat(List.of(history.get(0).get("status").asText(), history.get(1).get("status").asText()))
                .containsExactly("COMPLETED", "FAILED");
        assertThat(history.get(1).get("riskScore").isNull()).isTrue();
    }

    @Test
    void analysesLeftUnfinishedByAStoppedBackendAreFailedAtStartupAndCanBeRequestedAgain() {
        Session user = register("restart");
        UUID callId = uploadCall(user, wav(1));
        UUID leftover = UUID.randomUUID();
        jdbc.update("insert into analyses (id, call_record_id, status, started_at) values (?, ?, 'PROCESSING', now())",
                leftover, callId);
        assertError(requestAnalysis(user, callId), HttpStatus.CONFLICT, "ANALYSIS_IN_PROGRESS");

        analysisService.run(null);

        JsonNode failed = latest(user, callId).getBody();
        assertThat(failed.get("id").asText()).isEqualTo(leftover.toString());
        assertFailedWithoutRisk(failed, "ANALYSIS_INTERRUPTED");
        assertThat(analyse(user, callId).get("status").asText()).isEqualTo("COMPLETED");
    }
}
