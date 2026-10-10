package com.ivpds.analysis;

import static com.ivpds.analysis.StubAiServer.dropConnection;
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * With automatic start on (the default outside tests), uploading a call is enough to get it analysed.
 * Real application, PostgreSQL and MinIO; the AI service is the local stub.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT, properties = "ivpds.analysis.auto-start=true")
@Import({TestcontainersConfig.class, MinioConfig.class})
class AnalysisAutoStartIntegrationTest extends AnalysisTestSupport {

    private static final StubAiServer ai = new StubAiServer();

    @DynamicPropertySource
    static void aiProperties(DynamicPropertyRegistry registry) {
        registry.add("ivpds.ai.base-url", ai::baseUrl);
    }

    @BeforeEach
    void resetStub() {
        ai.reset();
    }

    @AfterAll
    static void stopStub() {
        ai.close();
    }

    @Test
    void uploadingACallStartsItsAnalysis() {
        Session user = register("auto");

        UUID callId = uploadCall(user, wav(1));

        JsonNode done = awaitFinished(user, callId);
        assertThat(done.get("status").asText()).isEqualTo("COMPLETED");
        assertThat(done.get("riskLevel").asText()).isEqualTo("HIGH");
        assertThat(get(user, "/api/v1/calls/" + callId + "/analyses").getBody()).hasSize(1);
    }

    @Test
    void anUploadSucceedsEvenWhenTheAiServiceIsDownAndTheAnalysisSaysWhy() {
        ai.onTranscription(dropConnection());
        Session user = register("down");

        // uploadCall asserts 201 Created.
        UUID callId = uploadCall(user, wav(1));

        assertFailedWithoutRisk(awaitFinished(user, callId), "AI_SERVICE_UNAVAILABLE");
        assertThat(get(user, "/api/v1/calls/" + callId).getBody().get("id").asText()).isEqualTo(callId.toString());
    }
}
