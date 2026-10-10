package com.ivpds.notification;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.ivpds.analysis.AnalysisTestSupport;
import com.ivpds.notification.StubPushServer.Received;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Device registration and push delivery over real HTTP against the real application, PostgreSQL and MinIO.
 * The Expo Push Service is replaced by a local stub, so these tests show what the backend sends and how it
 * reads the answers; they do not show that a phone receives anything.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT, properties = {
        "ivpds.bootstrap.admin.email=admin@push.test",
        "ivpds.bootstrap.admin.password=admin-password-1",
        "ivpds.push.enabled=true",
        "ivpds.push.access-token=test-expo-access-token",
        "ivpds.push.request-timeout=2s",
})
@Import({TestcontainersConfig.class, MinioConfig.class})
class PushNotificationIntegrationTest extends AnalysisTestSupport {

    private static final String DEVICES = "/api/v1/notifications/devices";
    private static final StubPushServer expo = new StubPushServer();
    private static final ObjectMapper json = new ObjectMapper();

    @DynamicPropertySource
    static void pushProperties(DynamicPropertyRegistry registry) {
        registry.add("ivpds.push.url", expo::url);
    }

    @BeforeEach
    void resetStub() {
        expo.reset();
    }

    @AfterAll
    static void stopStub() {
        expo.close();
    }

    // ----------------------------------------------------------------- devices

    @Test
    void aUserRegistersListsAndRemovesTheirDevices() {
        Session user = register("devices");
        Session other = register("devices-other");
        String phone = token();
        String tablet = token();

        ResponseEntity<JsonNode> registered = register(user, phone, "ANDROID");

        assertThat(registered.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(registered.getBody().get("token").asText()).isEqualTo(phone);
        assertThat(registered.getBody().get("platform").asText()).isEqualTo("ANDROID");
        assertThat(registered.getBody().get("id").asText()).isNotBlank();
        assertThat(registered.getBody().get("createdAt").isNull()).isFalse();
        register(user, tablet, "IOS");
        // Registering again (the app does it at every sign-in) keeps one row per token.
        assertThat(register(user, phone, "ANDROID").getBody().get("id").asText())
                .isEqualTo(registered.getBody().get("id").asText());
        assertThat(tokens(user)).containsExactlyInAnyOrder(phone, tablet);
        assertThat(tokens(other)).isEmpty();

        // Nobody can remove another user's device; removing twice is harmless.
        assertThat(unregister(other, phone).getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(tokens(user)).containsExactlyInAnyOrder(phone, tablet);
        assertThat(unregister(user, phone).getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(unregister(user, phone).getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(tokens(user)).containsExactly(tablet);
    }

    @Test
    void aTokenBelongsToWhoeverSignedInOnTheDeviceLast() {
        Session first = register("handover-a");
        Session second = register("handover-b");
        String shared = token();
        register(first, shared, "ANDROID");

        register(second, shared, "ANDROID");

        assertThat(tokens(first)).isEmpty();
        assertThat(tokens(second)).containsExactly(shared);
    }

    @Test
    void badRegistrationsAreRefusedAndTheNumberOfDevicesIsCapped() {
        Session user = register("bad-device");

        assertThat(register(Session.ANONYMOUS, token(), "IOS").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get(Session.ANONYMOUS, DEVICES).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertError(register(user, "not-an-expo-token", "IOS"), HttpStatus.BAD_REQUEST, "VALIDATION_FAILED");
        assertError(send(user, HttpMethod.PUT, DEVICES, Map.of("platform", "IOS")), HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED");
        assertError(send(user, HttpMethod.PUT, DEVICES, Map.of("token", token())), HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED");
        assertThat(register(user, token(), "SYMBIAN").getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(tokens(user)).isEmpty();

        List<String> registered = new ArrayList<>();
        for (int i = 0; i < PushDeviceController.MAX_DEVICES_PER_USER + 2; i++) {
            registered.add(token());
            register(user, registered.get(i), "ANDROID");
            // Keep "last seen" strictly increasing so the oldest device is well defined.
            sleep(5);
        }
        // The devices used least recently were dropped.
        assertThat(tokens(user)).containsExactlyInAnyOrderElementsOf(registered.subList(2, registered.size()));
    }

    // -------------------------------------------------------------------- push

    @Test
    void aNewNotificationIsPushedToEveryDeviceOfItsUserAndToNobodyElse() throws Exception {
        Session admin = admin();
        Session user = register("pushed");
        Session bystander = register("pushed-bystander");
        String phone = token();
        String tablet = token();
        register(user, phone, "ANDROID");
        register(user, tablet, "IOS");
        register(bystander, token(), "ANDROID");
        blacklist(admin, "0951000001", "Giả danh công an");
        expo.answer(200, "{\"data\":[" + StubPushServer.ok() + "," + StubPushServer.ok() + "]}");

        UUID callId = uploadCall(user, wav(1), "0951000001");

        await(() -> !expo.received().isEmpty());
        sleep(300);
        assertThat(expo.received()).hasSize(1);
        Received request = expo.received().get(0);
        assertThat(request.authorization()).isEqualTo("Bearer test-expo-access-token");
        assertThat(request.contentType()).startsWith("application/json");
        JsonNode messages = json.readTree(request.body());
        assertThat(messages).hasSize(2);
        assertThat(messages).extracting(message -> message.get("to").asText())
                .containsExactlyInAnyOrder(phone, tablet);
        // The push carries exactly the stored notification.
        JsonNode stored = get(user, "/api/v1/notifications").getBody().get("items").get(0);
        for (JsonNode message : messages) {
            assertThat(message.get("title").asText()).isEqualTo(stored.get("title").asText());
            assertThat(message.get("body").asText()).isEqualTo(stored.get("message").asText())
                    .contains("+84951000001", "Giả danh công an");
            assertThat(message.get("priority").asText()).isEqualTo("high");
            assertThat(message.get("data").get("notificationId").asText()).isEqualTo(stored.get("id").asText());
            assertThat(message.get("data").get("type").asText()).isEqualTo("BLACKLISTED_CALLER");
            assertThat(message.get("data").get("callId").asText()).isEqualTo(callId.toString());
            assertThat(message.get("data").get("analysisId").isNull()).isTrue();
        }
    }

    @Test
    void aUserWithoutDevicesGetsTheNotificationButNothingIsSent() {
        Session admin = admin();
        Session user = register("no-device");
        blacklist(admin, "0952000001", "Lừa đảo");

        uploadCall(user, wav(1), "0952000001");

        sleep(500);
        assertThat(expo.received()).isEmpty();
        assertThat(get(user, "/api/v1/notifications").getBody().get("totalItems").asInt()).isEqualTo(1);
    }

    @Test
    void aTokenThePushServiceNoLongerKnowsIsForgottenAndOtherRefusalsAreKept() {
        Session admin = admin();
        Session user = register("dead-token");
        String alive = token();
        String dead = token();
        String throttled = token();
        for (String token : List.of(alive, dead, throttled)) {
            register(user, token, "ANDROID");
            sleep(5);
        }
        blacklist(admin, "0953000001", "Lừa đảo");
        // Tickets come back in the order of the messages: newest device first.
        expo.answer(200, "{\"data\":[" + StubPushServer.refused("MessageRateExceeded") + ","
                + StubPushServer.refused("DeviceNotRegistered") + "," + StubPushServer.ok() + "]}");

        uploadCall(user, wav(1), "0953000001");

        await(() -> tokens(user).size() == 2);
        assertThat(tokens(user)).containsExactlyInAnyOrder(alive, throttled);
    }

    @Test
    void aFailingPushServiceNeverCostsTheUserTheirNotification() {
        Session admin = admin();
        Session user = register("push-down");
        String token = token();
        register(user, token, "ANDROID");
        blacklist(admin, "0954000001", "Lừa đảo");

        for (String[] failure : new String[][] {{"500", "{\"errors\":[{\"code\":\"INTERNAL\"}]}"},
                {"200", "this is not json"}, {"200", "{\"unexpected\":true}"}}) {
            expo.reset();
            expo.answer(Integer.parseInt(failure[0]), failure[1]);
            int before = get(user, "/api/v1/notifications").getBody().get("totalItems").asInt();

            UUID callId = uploadCall(user, wav(1), "0954000001");

            await(() -> !expo.received().isEmpty());
            sleep(200);
            JsonNode list = get(user, "/api/v1/notifications").getBody();
            assertThat(list.get("totalItems").asInt()).as(failure[1]).isEqualTo(before + 1);
            assertThat(list.get("items").get(0).get("callId").asText()).isEqualTo(callId.toString());
            // The device stays registered: the failure says nothing about the token.
            assertThat(tokens(user)).containsExactly(token);
        }
    }

    // ----------------------------------------------------------------- helpers

    private Session admin() {
        return login("admin@push.test", "admin-password-1");
    }

    private static String token() {
        return "ExponentPushToken[" + UUID.randomUUID().toString().replace("-", "") + "]";
    }

    private ResponseEntity<JsonNode> register(Session user, String token, String platform) {
        return send(user, HttpMethod.PUT, DEVICES, Map.of("token", token, "platform", platform));
    }

    private ResponseEntity<JsonNode> unregister(Session user, String token) {
        return rest.exchange(DEVICES + "?token={token}", HttpMethod.DELETE, new HttpEntity<>(bearer(user)),
                JsonNode.class, token);
    }

    private List<String> tokens(Session user) {
        List<String> tokens = new ArrayList<>();
        get(user, DEVICES).getBody().forEach(device -> tokens.add(device.get("token").asText()));
        return tokens;
    }

    private void blacklist(Session admin, String phoneNumber, String reason) {
        assertThat(send(admin, HttpMethod.POST, "/api/v1/admin/blacklist",
                Map.of("phoneNumber", phoneNumber, "reason", reason)).getStatusCode()).isEqualTo(HttpStatus.CREATED);
    }

    private static void await(BooleanSupplier condition) {
        long deadline = System.nanoTime() + 10_000_000_000L;
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            sleep(50);
        }
        throw new AssertionError("The expected push activity did not happen in time");
    }
}
