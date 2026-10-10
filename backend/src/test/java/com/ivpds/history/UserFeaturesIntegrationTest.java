package com.ivpds.history;

import static com.ivpds.analysis.StubAiServer.error;
import static com.ivpds.analysis.StubAiServer.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.ivpds.analysis.AnalysisTestSupport;
import com.ivpds.analysis.StubAiServer;
import com.ivpds.audio.StorageProperties;
import java.time.Instant;
import java.util.ArrayList;
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
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import software.amazon.awssdk.services.s3.S3Client;

/**
 * History, blacklist lookup and alerts, notifications and call deletion over real HTTP against the real
 * application, PostgreSQL and MinIO. The AI service is the local stub, scripted to give each risk level.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT, properties = {
        "ivpds.bootstrap.admin.email=admin@features.test",
        "ivpds.bootstrap.admin.password=admin-password-1",
})
@Import({TestcontainersConfig.class, MinioConfig.class})
class UserFeaturesIntegrationTest extends AnalysisTestSupport {

    private static final StubAiServer ai = new StubAiServer();

    @Autowired
    private S3Client s3;
    @Autowired
    private StorageProperties storage;

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

    // ----------------------------------------------------------------- history

    @Test
    void historyShowsEachCallWithItsLatestAnalysisAndCanBeFilteredAndPaged() {
        Session user = register("history");
        Instant before = Instant.now().minusSeconds(1);
        UUID high = analysed(user, "HIGH", 97, "0901000001");
        UUID medium = analysed(user, "MEDIUM", 45, "0901000002");
        UUID low = analysed(user, "LOW", 5, "0902000003");
        ai.reset();
        ai.onTranscription(error(503, "STT_UNAVAILABLE"));
        UUID failed = uploadCall(user, wav(1), "0902000004");
        analyse(user, failed);
        UUID never = uploadCall(user, wav(1));

        JsonNode all = history(user, "").getBody();
        assertThat(all.get("totalItems").asInt()).isEqualTo(5);
        assertThat(ids(all)).containsExactly(never, failed, low, medium, high);

        JsonNode top = all.get("items").get(4);
        assertThat(top.get("callerNumber").asText()).isEqualTo("+84901000001");
        assertThat(top.get("source").asText()).isEqualTo("UPLOADED");
        assertThat(top.get("durationSeconds").decimalValue()).isEqualByComparingTo("2");
        assertThat(top.get("analysis").get("status").asText()).isEqualTo("COMPLETED");
        assertThat(top.get("analysis").get("riskScore").asInt()).isEqualTo(97);
        assertThat(top.get("analysis").get("riskLevel").asText()).isEqualTo("HIGH");
        assertThat(top.get("analysis").get("indicators")).extracting(JsonNode::asText)
                .containsExactly("BANK_IMPERSONATION", "OTP_REQUEST");
        // The list does not carry transcripts; the owner block is for administrators only.
        assertThat(top.get("analysis").get("transcript").isNull()).isTrue();
        assertThat(top.get("owner").isNull()).isTrue();
        // A failed analysis has a code and no risk; a call never analysed has no analysis at all.
        JsonNode failedItem = all.get("items").get(1);
        assertThat(failedItem.get("analysis").get("errorCode").asText()).isEqualTo("STT_UNAVAILABLE");
        assertThat(failedItem.get("analysis").get("riskLevel").isNull()).isTrue();
        assertThat(all.get("items").get(0).get("analysis").isNull()).isTrue();

        assertThat(ids(history(user, "?riskLevel=HIGH").getBody())).containsExactly(high);
        assertThat(ids(history(user, "?riskLevel=LOW").getBody())).containsExactly(low);
        assertThat(ids(history(user, "?status=FAILED").getBody())).containsExactly(failed);
        assertThat(ids(history(user, "?status=COMPLETED").getBody())).containsExactly(low, medium, high);
        // Phone search ignores spacing and the leading zero of the national form.
        assertThat(ids(history(user, "?callerNumber=0901 000").getBody())).containsExactly(medium, high);
        assertThat(ids(history(user, "?callerNumber=84 902").getBody())).containsExactly(failed, low);
        assertThat(ids(history(user, "?from=" + before + "&to=" + Instant.now().plusSeconds(5)).getBody())).hasSize(5);
        assertThat(ids(history(user, "?to=" + before).getBody())).isEmpty();
        assertThat(ids(history(user, "?from=" + Instant.now().plusSeconds(60)).getBody())).isEmpty();

        JsonNode secondPage = history(user, "?size=2&page=1").getBody();
        assertThat(ids(secondPage)).containsExactly(low, medium);
        assertThat(secondPage.get("totalPages").asInt()).isEqualTo(3);
        assertError(history(user, "?riskLevel=EXTREME"), HttpStatus.BAD_REQUEST, "BAD_REQUEST");
    }

    @Test
    void historyDetailCarriesTheTranscriptAndIsOnlyForTheOwner() {
        Session owner = register("detail");
        Session other = register("stranger");
        UUID callId = analysed(owner, "HIGH", 97, "0903000001");

        JsonNode detail = get(owner, "/api/v1/history/" + callId).getBody();

        assertThat(detail.get("callId").asText()).isEqualTo(callId.toString());
        assertThat(detail.get("analysis").get("transcript").asText()).isEqualTo(StubAiServer.TRANSCRIPT);
        assertThat(detail.get("analysis").get("details").get("nlpModelVersion").asText()).isEqualTo("stub-model-1");
        assertThat(detail.get("analysis").get("details").get("sttModel").asText()).isEqualTo("stub-whisper");
        assertThat(get(Session.ANONYMOUS, "/api/v1/history").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertError(get(other, "/api/v1/history/" + callId), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertThat(history(other, "").getBody().get("totalItems").asInt()).isZero();
    }

    // ------------------------------------------------------------ notifications

    @Test
    void riskyCallsCreateNotificationsThatCanBeListedCountedAndMarkedRead() {
        Session user = register("notify");
        Session other = register("notify-other");
        UUID high = analysed(user, "HIGH", 97, "0904000001");
        UUID medium = analysed(user, "MEDIUM", 45, null);
        analysed(user, "LOW", 5, null);
        ai.reset();
        ai.onTranscription(error(503, "STT_UNAVAILABLE"));
        analyse(user, uploadCall(user, wav(1)));

        JsonNode list = get(user, "/api/v1/notifications").getBody();

        // Only the HIGH and the MEDIUM call notify; LOW and failed analyses do not.
        assertThat(list.get("totalItems").asInt()).isEqualTo(2);
        JsonNode newest = list.get("items").get(0);
        JsonNode oldest = list.get("items").get(1);
        assertThat(newest.get("type").asText()).isEqualTo("SUSPICIOUS_CALL");
        assertThat(newest.get("callId").asText()).isEqualTo(medium.toString());
        assertThat(oldest.get("type").asText()).isEqualTo("HIGH_RISK_CALL");
        assertThat(oldest.get("callId").asText()).isEqualTo(high.toString());
        assertThat(oldest.get("analysisId").isNull()).isFalse();
        assertThat(oldest.get("message").asText()).contains("+84904000001", "97/100");
        assertThat(oldest.get("read").asBoolean()).isFalse();
        assertThat(unread(user)).isEqualTo(2);

        UUID oldestId = UUID.fromString(oldest.get("id").asText());
        JsonNode read = send(user, HttpMethod.POST, "/api/v1/notifications/" + oldestId + "/read", null).getBody();
        assertThat(read.get("read").asBoolean()).isTrue();
        assertThat(read.get("readAt").isNull()).isFalse();
        assertThat(unread(user)).isEqualTo(1);
        JsonNode unreadOnly = get(user, "/api/v1/notifications?unreadOnly=true").getBody();
        assertThat(unreadOnly.get("totalItems").asInt()).isEqualTo(1);
        assertThat(unreadOnly.get("items").get(0).get("type").asText()).isEqualTo("SUSPICIOUS_CALL");

        // Notifications are private.
        assertThat(get(other, "/api/v1/notifications").getBody().get("totalItems").asInt()).isZero();
        assertError(send(other, HttpMethod.POST, "/api/v1/notifications/" + oldestId + "/read", null),
                HttpStatus.NOT_FOUND, "NOTIFICATION_NOT_FOUND");
        assertThat(get(Session.ANONYMOUS, "/api/v1/notifications").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);

        assertThat(send(user, HttpMethod.POST, "/api/v1/notifications/read-all", null).getBody().get("marked").asInt())
                .isEqualTo(1);
        assertThat(unread(user)).isZero();
        assertThat(send(user, HttpMethod.POST, "/api/v1/notifications/read-all", null).getBody().get("marked").asInt())
                .isZero();
    }

    // ---------------------------------------------------------------- blacklist

    @Test
    void anyUserCanLookUpANumberInWhateverFormatTheyTypeIt() {
        Session admin = login("admin@features.test", "admin-password-1");
        Session user = register("lookup");
        blacklist(admin, "0905 111 222", "Giả danh ngân hàng");

        for (String typed : List.of("0905111222", "0905.111.222", "+84905111222", "84905111222")) {
            JsonNode found = lookup(user, typed).getBody();
            assertThat(found.get("blacklisted").asBoolean()).as(typed).isTrue();
            assertThat(found.get("phoneNumber").asText()).isEqualTo("+84905111222");
            assertThat(found.get("reason").asText()).isEqualTo("Giả danh ngân hàng");
            assertThat(found.get("since").isNull()).isFalse();
        }
        JsonNode clean = lookup(user, "0905111223").getBody();
        assertThat(clean.get("blacklisted").asBoolean()).isFalse();
        assertThat(clean.get("reason").isNull()).isTrue();
        assertError(lookup(user, "not a number"), HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");
        assertThat(lookup(Session.ANONYMOUS, "0905111222").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        // Looking numbers up is for everyone; changing the list is not.
        assertThat(send(user, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("phoneNumber", "0905111999"))
                .getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void aCallFromABlacklistedNumberWarnsTheUserUnlessTheyTurnedAlertsOff() {
        Session admin = login("admin@features.test", "admin-password-1");
        JsonNode entry = blacklist(admin, "0906111222", "Giả danh công an");
        Session alerted = register("alerted");
        Session muted = register("muted");
        assertThat(send(muted, HttpMethod.PATCH, "/api/v1/users/me", Map.of("blacklistAlertEnabled", false))
                .getStatusCode()).isEqualTo(HttpStatus.OK);

        UUID uploaded = uploadCall(alerted, wav(1), "0906 111 222");
        uploadCall(alerted, wav(1), "0906111223");
        uploadCall(muted, wav(1), "0906111222");
        // A live call warns as soon as it is opened, before any audio.
        UUID live = UUID.fromString(send(alerted, HttpMethod.POST, "/api/v1/live-calls",
                Map.of("callerNumber", "0906111222")).getBody().get("callId").asText());

        JsonNode list = get(alerted, "/api/v1/notifications").getBody();
        assertThat(list.get("totalItems").asInt()).isEqualTo(2);
        assertThat(list.get("items")).allSatisfy(item -> {
            assertThat(item.get("type").asText()).isEqualTo("BLACKLISTED_CALLER");
            assertThat(item.get("message").asText()).contains("+84906111222", "Giả danh công an");
            assertThat(item.get("analysisId").isNull()).isTrue();
        });
        assertThat(list.get("items")).extracting(item -> item.get("callId").asText())
                .containsExactly(live.toString(), uploaded.toString());
        assertThat(get(muted, "/api/v1/notifications").getBody().get("totalItems").asInt()).isZero();
        // History marks the caller as blacklisted for both users, whatever their alert setting.
        assertThat(get(alerted, "/api/v1/history/" + uploaded).getBody().get("callerBlacklisted").asBoolean()).isTrue();
        assertThat(history(muted, "").getBody().get("items").get(0).get("callerBlacklisted").asBoolean()).isTrue();

        // Once the entry is switched off, the number is clean again everywhere.
        send(admin, HttpMethod.PATCH, "/api/v1/admin/blacklist/" + entry.get("id").asText(), Map.of("active", false));
        uploadCall(alerted, wav(1), "0906111222");
        assertThat(get(alerted, "/api/v1/notifications").getBody().get("totalItems").asInt()).isEqualTo(2);
        assertThat(lookup(alerted, "0906111222").getBody().get("blacklisted").asBoolean()).isFalse();
        assertThat(get(alerted, "/api/v1/history/" + uploaded).getBody().get("callerBlacklisted").asBoolean()).isFalse();
    }

    // ------------------------------------------------------------------ delete

    @Test
    void deletingACallRemovesItsAudioAnalysesAndHistoryAndOnlyTheOwnerCanDoIt() {
        Session owner = register("delete");
        Session other = register("delete-other");
        UUID callId = analysed(owner, "HIGH", 97, "0907000001");
        UUID kept = analysed(owner, "LOW", 5, null);
        String key = jdbc.queryForObject("select object_key from audio_files where call_record_id = ?", String.class,
                callId);
        UUID notification = UUID.fromString(get(owner, "/api/v1/notifications").getBody().get("items").get(0)
                .get("id").asText());

        assertError(send(other, HttpMethod.DELETE, "/api/v1/calls/" + callId, null), HttpStatus.NOT_FOUND,
                "CALL_NOT_FOUND");
        assertThat(send(Session.ANONYMOUS, HttpMethod.DELETE, "/api/v1/calls/" + callId, null).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(send(owner, HttpMethod.DELETE, "/api/v1/calls/" + callId, null).getStatusCode())
                .isEqualTo(HttpStatus.NO_CONTENT);

        assertError(get(owner, "/api/v1/calls/" + callId), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(get(owner, "/api/v1/history/" + callId), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertThat(ids(history(owner, "").getBody())).containsExactly(kept);
        for (String table : List.of("audio_files", "analyses")) {
            assertThat(count(table, "call_record_id", callId)).as(table).isZero();
        }
        assertThat(s3.listObjectsV2(b -> b.bucket(storage.bucket()).prefix(key)).contents()).isEmpty();
        // The notification survives without pointing at the deleted call.
        JsonNode orphan = get(owner, "/api/v1/notifications").getBody().get("items").get(0);
        assertThat(orphan.get("id").asText()).isEqualTo(notification.toString());
        assertThat(orphan.get("callId").isNull()).isTrue();
        assertError(send(owner, HttpMethod.DELETE, "/api/v1/calls/" + callId, null), HttpStatus.NOT_FOUND,
                "CALL_NOT_FOUND");
    }

    @Test
    void aCallCannotBeDeletedWhileItIsBeingAnalysed() throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ai.onTranscription((exchange, body) -> {
            entered.countDown();
            try {
                release.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            json(200, StubAiServer.transcriptionBody(StubAiServer.TRANSCRIPT)).handle(exchange, body);
        });
        Session user = register("busy");
        UUID callId = uploadCall(user, wav(1));
        requestAnalysis(user, callId);
        assertThat(entered.await(10, TimeUnit.SECONDS)).isTrue();

        assertError(send(user, HttpMethod.DELETE, "/api/v1/calls/" + callId, null), HttpStatus.CONFLICT,
                "ANALYSIS_IN_PROGRESS");

        release.countDown();
        awaitFinished(user, callId);
        assertThat(send(user, HttpMethod.DELETE, "/api/v1/calls/" + callId, null).getStatusCode())
                .isEqualTo(HttpStatus.NO_CONTENT);
    }

    // ----------------------------------------------------------------- helpers

    /** Uploads a call and has the stub answer its analysis with the given risk. */
    private UUID analysed(Session user, String level, int score, String callerNumber) {
        ai.reset();
        ai.onRisk(json(200, StubAiServer.riskBody(score, level, 0.9)));
        UUID callId = callerNumber == null ? uploadCall(user, wav(2)) : uploadCall(user, wav(2), callerNumber);
        assertThat(analyse(user, callId).get("riskLevel").asText()).isEqualTo(level);
        return callId;
    }

    private ResponseEntity<JsonNode> history(Session user, String query) {
        return get(user, "/api/v1/history" + query);
    }

    private ResponseEntity<JsonNode> lookup(Session user, String phoneNumber) {
        return rest.exchange("/api/v1/blacklist/lookup?phoneNumber={number}", HttpMethod.GET,
                new org.springframework.http.HttpEntity<>(bearer(user)), JsonNode.class, phoneNumber);
    }

    private JsonNode blacklist(Session admin, String phoneNumber, String reason) {
        ResponseEntity<JsonNode> response = send(admin, HttpMethod.POST, "/api/v1/admin/blacklist",
                Map.of("phoneNumber", phoneNumber, "reason", reason));
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        return response.getBody();
    }

    private long unread(Session user) {
        return get(user, "/api/v1/notifications/unread-count").getBody().get("unreadCount").asLong();
    }

    private static List<UUID> ids(JsonNode page) {
        List<UUID> ids = new ArrayList<>();
        page.get("items").forEach(item -> ids.add(UUID.fromString(item.get("callId").asText())));
        return ids;
    }
}
