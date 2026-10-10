package com.ivpds.admin;

import static com.ivpds.analysis.StubAiServer.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.ivpds.analysis.AnalysisTestSupport;
import com.ivpds.analysis.StubAiServer;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * The administrator API over real HTTP against the real application, PostgreSQL and MinIO: accounts, blacklist,
 * phishing patterns, calls of all users and statistics. The AI service is the local stub.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT, properties = {
        "ivpds.bootstrap.admin.email=admin@admin.test",
        "ivpds.bootstrap.admin.password=admin-password-1",
})
@Import({TestcontainersConfig.class, MinioConfig.class})
class AdminApiIntegrationTest extends AnalysisTestSupport {

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

    // ------------------------------------------------------------ authorization

    @Test
    void everyAdminEndpointIsClosedToOrdinaryUsersAndToAnonymousCallers() {
        Session user = register("plain");
        UUID any = UUID.randomUUID();
        Map<String, HttpMethod> endpoints = new HashMap<>();
        for (String path : List.of("/users", "/users/" + any, "/calls", "/calls/" + any, "/statistics", "/blacklist",
                "/blacklist/reports",
                "/phishing-patterns", "/phishing-patterns/" + any)) {
            endpoints.put(path, HttpMethod.GET);
        }
        endpoints.put("/users/" + any + "/status", HttpMethod.PATCH);
        endpoints.put("/blacklist/" + any, HttpMethod.DELETE);
        endpoints.put("/phishing-patterns/" + any + "/", HttpMethod.DELETE);

        endpoints.forEach((path, method) -> {
            Object body = method == HttpMethod.PATCH ? Map.of("status", "LOCKED") : null;
            assertThat(send(user, method, "/api/v1/admin" + path, body).getStatusCode()).as(path)
                    .isEqualTo(HttpStatus.FORBIDDEN);
            assertThat(send(Session.ANONYMOUS, method, "/api/v1/admin" + path, body).getStatusCode()).as(path)
                    .isEqualTo(HttpStatus.UNAUTHORIZED);
        });
        assertThat(send(user, HttpMethod.POST, "/api/v1/admin/phishing-patterns",
                Map.of("name", "x", "indicatorCode", "OTP_REQUEST", "pattern", "y")).getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
    }

    // -------------------------------------------------------------------- users

    @Test
    void adminsCanSearchAccountsAndLockAndUnlockThem() {
        Session admin = admin();
        Session target = register("lockme");
        register("bystander");

        JsonNode found = send(admin, HttpMethod.GET, "/api/v1/admin/users?query=LOCKME", null).getBody();
        assertThat(found.get("totalItems").asInt()).isEqualTo(1);
        JsonNode account = found.get("items").get(0);
        assertThat(account.get("email").asText()).isEqualTo(target.email());
        assertThat(account.get("status").asText()).isEqualTo("ACTIVE");
        assertThat(account.get("roles")).extracting(JsonNode::asText).containsExactly("USER");
        assertThat(account.toString()).doesNotContain("password");
        // The search also reads full names.
        assertThat(send(admin, HttpMethod.GET, "/api/v1/admin/users?query=test user lockme", null).getBody()
                .get("totalItems").asInt()).isEqualTo(1);
        assertThat(send(admin, HttpMethod.GET, "/api/v1/admin/users/" + target.id(), null).getBody().get("id").asText())
                .isEqualTo(target.id().toString());

        ResponseEntity<JsonNode> locked = send(admin, HttpMethod.PATCH, "/api/v1/admin/users/" + target.id() + "/status",
                Map.of("status", "LOCKED"));
        assertThat(locked.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(locked.getBody().get("status").asText()).isEqualTo("LOCKED");
        // The lock takes effect at once: the access token the user already holds is refused.
        assertThat(get(target, "/api/v1/users/me").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get(target, "/api/v1/history").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        // A locked account cannot sign in either, and its refresh token no longer works.
        assertError(loginAttempt(target.email(), password()), HttpStatus.FORBIDDEN, "ACCOUNT_LOCKED");
        assertThat(rest.postForEntity("/api/v1/auth/refresh", Map.of("refreshToken", target.refreshToken()),
                JsonNode.class).getStatusCode().is4xxClientError()).isTrue();
        JsonNode lockedOnly = send(admin, HttpMethod.GET, "/api/v1/admin/users?status=LOCKED", null).getBody();
        assertThat(lockedOnly.get("items")).extracting(item -> item.get("email").asText()).contains(target.email());
        assertThat(lockedOnly.get("items")).allSatisfy(item -> assertThat(item.get("status").asText())
                .isEqualTo("LOCKED"));

        send(admin, HttpMethod.PATCH, "/api/v1/admin/users/" + target.id() + "/status", Map.of("status", "ACTIVE"));
        assertThat(loginAttempt(target.email(), password()).getStatusCode()).isEqualTo(HttpStatus.OK);
        // The token issued before the lock is accepted again once the account is unlocked (until it expires).
        assertThat(get(target, "/api/v1/users/me").getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void anAdminCannotLockThemselvesAndBadRequestsAreRefused() {
        Session admin = admin();
        String self = "/api/v1/admin/users/" + admin.id() + "/status";

        assertError(send(admin, HttpMethod.PATCH, self, Map.of("status", "LOCKED")), HttpStatus.CONFLICT,
                "CANNOT_LOCK_OWN_ACCOUNT");
        assertThat(send(admin, HttpMethod.PATCH, self, Map.of("status", "ACTIVE")).getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(send(admin, HttpMethod.PATCH, self, Map.of("status", "BANNED")).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(send(admin, HttpMethod.PATCH, self, Map.of()).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertError(send(admin, HttpMethod.GET, "/api/v1/admin/users/" + UUID.randomUUID(), null),
                HttpStatus.NOT_FOUND, "USER_NOT_FOUND");
    }

    // ---------------------------------------------------------------- blacklist

    @Test
    void adminsManageTheBlacklist() {
        Session admin = admin();
        ResponseEntity<JsonNode> created = send(admin, HttpMethod.POST, "/api/v1/admin/blacklist",
                Map.of("phoneNumber", "0911 222 333", "reason", "  Giả danh ngân hàng  "));

        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        JsonNode entry = created.getBody();
        String id = entry.get("id").asText();
        assertThat(entry.get("phoneNumber").asText()).isEqualTo("+84911222333");
        assertThat(entry.get("reason").asText()).isEqualTo("Giả danh ngân hàng");
        assertThat(entry.get("active").asBoolean()).isTrue();
        assertThat(entry.get("createdBy").asText()).isEqualTo(admin.id().toString());
        // The same number in another spelling is a duplicate.
        assertError(send(admin, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("phoneNumber", "+84911222333")),
                HttpStatus.CONFLICT, "PHONE_NUMBER_ALREADY_BLACKLISTED");
        assertError(send(admin, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("phoneNumber", "abc")),
                HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");
        assertError(send(admin, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("reason", "no number")),
                HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");

        send(admin, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("phoneNumber", "0911222444"));
        assertThat(numbers(send(admin, HttpMethod.GET, "/api/v1/admin/blacklist?query=0911 222", null).getBody()))
                .containsExactly("+84911222444", "+84911222333");

        JsonNode updated = send(admin, HttpMethod.PATCH, "/api/v1/admin/blacklist/" + id,
                Map.of("reason", "Giả danh công an", "active", false)).getBody();
        assertThat(updated.get("reason").asText()).isEqualTo("Giả danh công an");
        assertThat(updated.get("active").asBoolean()).isFalse();
        assertThat(numbers(send(admin, HttpMethod.GET, "/api/v1/admin/blacklist?query=0911222&active=true", null)
                .getBody())).containsExactly("+84911222444");
        assertThat(numbers(send(admin, HttpMethod.GET, "/api/v1/admin/blacklist?query=0911222&active=false", null)
                .getBody())).containsExactly("+84911222333");

        assertThat(send(admin, HttpMethod.DELETE, "/api/v1/admin/blacklist/" + id, null).getStatusCode())
                .isEqualTo(HttpStatus.NO_CONTENT);
        assertError(send(admin, HttpMethod.DELETE, "/api/v1/admin/blacklist/" + id, null), HttpStatus.NOT_FOUND,
                "BLACKLIST_ENTRY_NOT_FOUND");
        // A deleted number can be added again.
        assertThat(send(admin, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("phoneNumber", "0911222333"))
                .getStatusCode()).isEqualTo(HttpStatus.CREATED);
    }

    // --------------------------------------------------------- phishing patterns

    @Test
    void adminsManagePhishingPatterns() {
        Session admin = admin();
        String base = "/api/v1/admin/phishing-patterns";
        String marker = "mau-" + UUID.randomUUID();

        ResponseEntity<JsonNode> created = send(admin, HttpMethod.POST, base, Map.of("name", "Đòi mã OTP " + marker,
                "indicatorCode", "OTP_REQUEST", "pattern", "đọc mã otp cho em", "description", "Kẻ gọi xin mã"));
        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        String id = created.getBody().get("id").asText();
        assertThat(created.getBody().get("active").asBoolean()).isTrue();
        assertThat(created.getBody().get("createdBy").asText()).isEqualTo(admin.id().toString());
        send(admin, HttpMethod.POST, base, Map.of("name", "Dọa khóa tài khoản " + marker,
                "indicatorCode", "ACCOUNT_LOCK_THREAT", "pattern", "tài khoản sẽ bị khóa"));

        for (Map<String, String> invalid : List.of(
                Map.of("indicatorCode", "OTP_REQUEST", "pattern", "x"),
                Map.of("name", " ", "indicatorCode", "OTP_REQUEST", "pattern", "x"),
                Map.of("name", "n", "indicatorCode", "otp request", "pattern", "x"),
                Map.of("name", "n", "indicatorCode", "OTP_REQUEST"))) {
            assertError(send(admin, HttpMethod.POST, base, invalid), HttpStatus.BAD_REQUEST, "VALIDATION_FAILED");
        }

        // Only what the rule engine can use is accepted: a known indicator and a phrase of two words or more.
        for (String code : List.of("MADE_UP_CODE", "COORDINATED_CALLERS")) {
            assertError(send(admin, HttpMethod.POST, base, Map.of("name", "n", "indicatorCode", code,
                    "pattern", "đọc mã otp")), HttpStatus.BAD_REQUEST, "UNKNOWN_INDICATOR_CODE");
        }
        assertError(send(admin, HttpMethod.POST, base, Map.of("name", "n", "indicatorCode", "OTP_REQUEST",
                "pattern", "otp")), HttpStatus.BAD_REQUEST, "PATTERN_TOO_SHORT");
        assertError(send(admin, HttpMethod.POST, base, Map.of("name", "n", "indicatorCode", "OTP_REQUEST",
                "pattern", "ab ".repeat(67))), HttpStatus.BAD_REQUEST, "VALIDATION_FAILED");
        assertError(send(admin, HttpMethod.PATCH, base + "/" + id, Map.of("pattern", "otp")), HttpStatus.BAD_REQUEST,
                "PATTERN_TOO_SHORT");
        assertError(send(admin, HttpMethod.PATCH, base + "/" + id, Map.of("indicatorCode", "MADE_UP_CODE")),
                HttpStatus.BAD_REQUEST, "UNKNOWN_INDICATOR_CODE");
        assertThat(send(admin, HttpMethod.GET, base + "/" + id, null).getBody().get("pattern").asText())
                .isEqualTo("đọc mã otp cho em");

        assertThat(names(send(admin, HttpMethod.GET, base + "?query=" + marker, null).getBody())).hasSize(2);
        assertThat(names(send(admin, HttpMethod.GET, base + "?query=" + marker + "&indicatorCode=OTP_REQUEST", null)
                .getBody())).containsExactly("Đòi mã OTP " + marker);
        // The search also reads the pattern text.
        assertThat(names(send(admin, HttpMethod.GET, base + "?query=SẼ BỊ KHÓA", null).getBody()))
                .contains("Dọa khóa tài khoản " + marker);

        JsonNode updated = send(admin, HttpMethod.PATCH, base + "/" + id,
                Map.of("pattern", "anh đọc mã otp", "active", false, "description", "")).getBody();
        assertThat(updated.get("pattern").asText()).isEqualTo("anh đọc mã otp");
        assertThat(updated.get("active").asBoolean()).isFalse();
        assertThat(updated.get("description").isNull()).isTrue();
        assertThat(updated.get("name").asText()).isEqualTo("Đòi mã OTP " + marker);
        assertThat(names(send(admin, HttpMethod.GET, base + "?query=" + marker + "&active=true", null).getBody()))
                .containsExactly("Dọa khóa tài khoản " + marker);
        assertError(send(admin, HttpMethod.PATCH, base + "/" + id, Map.of("name", "  ")), HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED");
        assertThat(send(admin, HttpMethod.GET, base + "/" + id, null).getBody().get("id").asText()).isEqualTo(id);

        assertThat(send(admin, HttpMethod.DELETE, base + "/" + id, null).getStatusCode())
                .isEqualTo(HttpStatus.NO_CONTENT);
        assertError(send(admin, HttpMethod.GET, base + "/" + id, null), HttpStatus.NOT_FOUND,
                "PHISHING_PATTERN_NOT_FOUND");
    }

    // -------------------------------------------------------------------- calls

    @Test
    void adminsSeeTheAnalysedCallsOfAllUsersWithTheirOwnersAndTranscripts() {
        Session admin = admin();
        Session alice = register("alice");
        Session bob = register("bob");
        UUID aliceHigh = analysed(alice, "HIGH", 97, "0921000001");
        UUID bobHigh = analysed(bob, "HIGH", 88, "0921000002");
        UUID bobLow = analysed(bob, "LOW", 3, "0921000003");

        JsonNode high = send(admin, HttpMethod.GET, "/api/v1/admin/calls?riskLevel=HIGH&callerNumber=0921000", null)
                .getBody();
        assertThat(ids(high)).containsExactly(bobHigh, aliceHigh);
        JsonNode first = high.get("items").get(0);
        assertThat(first.get("owner").get("email").asText()).isEqualTo(bob.email());
        assertThat(first.get("owner").get("id").asText()).isEqualTo(bob.id().toString());
        assertThat(first.get("analysis").get("riskScore").asInt()).isEqualTo(88);
        assertThat(first.get("analysis").get("transcript").isNull()).isTrue();

        assertThat(ids(send(admin, HttpMethod.GET, "/api/v1/admin/calls?userId=" + bob.id(), null).getBody()))
                .containsExactly(bobLow, bobHigh);
        assertThat(ids(send(admin, HttpMethod.GET, "/api/v1/admin/calls?userId=" + bob.id() + "&riskLevel=LOW", null)
                .getBody())).containsExactly(bobLow);

        JsonNode detail = send(admin, HttpMethod.GET, "/api/v1/admin/calls/" + aliceHigh, null).getBody();
        assertThat(detail.get("owner").get("email").asText()).isEqualTo(alice.email());
        assertThat(detail.get("analysis").get("transcript").asText()).isEqualTo(StubAiServer.TRANSCRIPT);
        assertThat(detail.get("analysis").get("details").get("riskEngineVersion").asText()).isEqualTo("stub-risk-1");
        assertError(send(admin, HttpMethod.GET, "/api/v1/admin/calls/" + UUID.randomUUID(), null),
                HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        // Administrators read results but cannot download a user's recording.
        assertThat(get(admin, "/api/v1/calls/" + aliceHigh + "/audio").getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    // --------------------------------------------------------------- statistics

    @Test
    void statisticsAreCountedFromTheDatabaseAndTheDailyReportCoversTheWholePeriod() {
        Session admin = admin();
        Session user = register("stats");
        analysed(user, "HIGH", 97, "0931000001");
        analysed(user, "MEDIUM", 45, null);
        uploadCall(user, wav(1));

        JsonNode stats = send(admin, HttpMethod.GET, "/api/v1/admin/statistics?days=7", null).getBody();

        assertThat(stats.get("periodDays").asInt()).isEqualTo(7);
        assertThat(stats.get("users").get("total").asLong()).isEqualTo(sql("select count(*) from users"));
        assertThat(stats.get("users").get("locked").asLong())
                .isEqualTo(sql("select count(*) from users where status = 'LOCKED'"));
        assertThat(stats.get("users").get("active").asLong() + stats.get("users").get("locked").asLong())
                .isEqualTo(stats.get("users").get("total").asLong());
        assertThat(stats.get("users").get("newInPeriod").asLong()).isEqualTo(stats.get("users").get("total").asLong());
        long calls = sql("select count(*) from call_records");
        assertThat(stats.get("calls").get("total").asLong()).isEqualTo(calls);
        assertThat(stats.get("calls").get("UPLOADED").asLong() + stats.get("calls").get("RECORDED").asLong()
                + stats.get("calls").get("LIVE").asLong()).isEqualTo(calls);
        assertThat(stats.get("analysesByStatus").get("COMPLETED").asLong())
                .isEqualTo(sql("select count(*) from analyses where status = 'COMPLETED'"));
        assertThat(stats.get("analysesByStatus").has("PENDING")).isTrue();
        for (String level : List.of("LOW", "MEDIUM", "HIGH")) {
            assertThat(stats.get("callsByRiskLevel").get(level).asLong()).as(level).isEqualTo(sql(
                    "select count(*) from risk_results where risk_level = '" + level + "'"));
        }
        assertThat(stats.get("callsByRiskLevel").get("HIGH").asLong()).isGreaterThanOrEqualTo(1);
        assertThat(stats.get("topIndicators")).isNotEmpty();
        JsonNode top = stats.get("topIndicators").get(0);
        assertThat(top.get("calls").asLong()).isEqualTo(sql(
                "select count(*) from risk_indicators where indicator_code = '" + top.get("indicator").asText() + "'"));
        assertThat(stats.get("blacklist").get("total").asLong()).isEqualTo(sql("select count(*) from blacklist_numbers"));
        assertThat(stats.get("phishingPatterns").get("active").asLong())
                .isEqualTo(sql("select count(*) from phishing_patterns where active"));

        // One row per day, oldest first, ending today in the time zone of the report (Vietnam by default).
        assertThat(stats.get("timeZone").asText()).isEqualTo("Asia/Ho_Chi_Minh");
        JsonNode daily = stats.get("daily");
        assertThat(daily).hasSize(7);
        LocalDate today = LocalDate.now(VIETNAM);
        assertThat(daily.get(0).get("date").asText()).isEqualTo(today.minusDays(6).toString());
        JsonNode last = daily.get(6);
        assertThat(last.get("date").asText()).isEqualTo(today.toString());
        long sum = 0;
        for (JsonNode day : daily) {
            sum += day.get("calls").asLong();
            assertThat(day.get("high").asLong() + day.get("medium").asLong() + day.get("low").asLong()
                    + day.get("unanalysed").asLong()).isEqualTo(day.get("calls").asLong());
        }
        assertThat(sum).isEqualTo(stats.get("calls").get("newInPeriod").asLong());
        assertThat(last.get("calls").asLong()).isEqualTo(sql(
                "select count(*) from call_records where (created_at at time zone 'Asia/Ho_Chi_Minh')::date = '"
                        + today + "'"));
        assertThat(last.get("high").asLong()).isGreaterThanOrEqualTo(1);
        assertThat(last.get("unanalysed").asLong()).isGreaterThanOrEqualTo(1);

        // The period is clamped to something sensible.
        assertThat(send(admin, HttpMethod.GET, "/api/v1/admin/statistics", null).getBody().get("daily")).hasSize(30);
        assertThat(send(admin, HttpMethod.GET, "/api/v1/admin/statistics?days=0", null).getBody().get("daily"))
                .hasSize(1);
        assertThat(send(admin, HttpMethod.GET, "/api/v1/admin/statistics?days=100000", null).getBody()
                .get("periodDays").asInt()).isEqualTo(365);
    }

    @Test
    void theDailyReportSplitsDaysInTheRequestedTimeZone() {
        Session admin = admin();
        Session user = register("zones");
        // 03:00 yesterday in Vietnam is 20:00 two days ago in UTC.
        LocalDate today = LocalDate.now(VIETNAM);
        Instant moment = today.minusDays(1).atTime(3, 0).atZone(VIETNAM).toInstant();
        jdbc.update("insert into call_records (user_id, source, created_at) values (?, 'UPLOADED', ?)", user.id(),
                Timestamp.from(moment));

        JsonNode vietnam = send(admin, HttpMethod.GET, "/api/v1/admin/statistics?days=7", null).getBody();
        JsonNode utc = send(admin, HttpMethod.GET, "/api/v1/admin/statistics?days=7&timeZone=UTC", null).getBody();

        assertThat(utc.get("timeZone").asText()).isEqualTo("UTC");
        assertThat(callsOn(vietnam, today.minusDays(1))).isEqualTo(1);
        assertThat(callsOn(vietnam, today.minusDays(2))).isZero();
        assertThat(callsOn(utc, today.minusDays(2))).isEqualTo(1);
        assertError(send(admin, HttpMethod.GET, "/api/v1/admin/statistics?timeZone=Mars/Olympus", null),
                HttpStatus.BAD_REQUEST, "INVALID_TIME_ZONE");
    }

    @Test
    void numbersWithHighRiskCallsAreSuggestedForTheBlacklistUntilTheyAreOnIt() {
        Session admin = admin();
        Session first = register("victim-a");
        Session second = register("victim-b");
        analysed(first, "HIGH", 97, "0941000001");
        analysed(second, "HIGH", 90, "0941 000 001");
        analysed(first, "HIGH", 91, "0941000002");
        analysed(first, "LOW", 4, "0941000003");
        analysed(first, "HIGH", 95, null);

        JsonNode suspected = send(admin, HttpMethod.GET, "/api/v1/admin/statistics", null).getBody()
                .get("suspectedNumbers");

        List<String> numbers = new ArrayList<>();
        suspected.forEach(item -> numbers.add(item.get("phoneNumber").asText()));
        // Most reported first; LOW calls and calls without a number are not suggestions.
        assertThat(numbers).contains("+84941000001", "+84941000002").doesNotContain("+84941000003");
        assertThat(numbers.indexOf("+84941000001")).isLessThan(numbers.indexOf("+84941000002"));
        JsonNode top = suspected.get(numbers.indexOf("+84941000001"));
        assertThat(top.get("highRiskCalls").asInt()).isEqualTo(2);
        assertThat(top.get("users").asInt()).isEqualTo(2);
        assertThat(top.get("lastCallAt").isNull()).isFalse();

        // Once the administrator blacklists a number it is no longer a suggestion.
        send(admin, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("phoneNumber", "0941000001"));
        List<String> after = new ArrayList<>();
        send(admin, HttpMethod.GET, "/api/v1/admin/statistics", null).getBody().get("suspectedNumbers")
                .forEach(item -> after.add(item.get("phoneNumber").asText()));
        assertThat(after).contains("+84941000002").doesNotContain("+84941000001");
    }

    // ----------------------------------------------------------------- helpers

    private static final ZoneId VIETNAM = ZoneId.of("Asia/Ho_Chi_Minh");

    private static long callsOn(JsonNode statistics, LocalDate date) {
        for (JsonNode day : statistics.get("daily")) {
            if (day.get("date").asText().equals(date.toString())) {
                return day.get("calls").asLong();
            }
        }
        throw new AssertionError("No row for " + date);
    }

    private Session admin() {
        return login("admin@admin.test", "admin-password-1");
    }

    private UUID analysed(Session user, String level, int score, String callerNumber) {
        ai.reset();
        ai.onRisk(json(200, StubAiServer.riskBody(score, level, 0.9)));
        UUID callId = callerNumber == null ? uploadCall(user, wav(1)) : uploadCall(user, wav(1), callerNumber);
        assertThat(analyse(user, callId).get("riskLevel").asText()).isEqualTo(level);
        return callId;
    }

    private long sql(String query) {
        return jdbc.queryForObject(query, Long.class);
    }

    private static List<UUID> ids(JsonNode page) {
        List<UUID> ids = new ArrayList<>();
        page.get("items").forEach(item -> ids.add(UUID.fromString(item.get("callId").asText())));
        return ids;
    }

    private static List<String> numbers(JsonNode page) {
        List<String> numbers = new ArrayList<>();
        page.get("items").forEach(item -> numbers.add(item.get("phoneNumber").asText()));
        return numbers;
    }

    private static List<String> names(JsonNode page) {
        List<String> names = new ArrayList<>();
        page.get("items").forEach(item -> names.add(item.get("name").asText()));
        return names;
    }
}
