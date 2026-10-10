package com.ivpds.blacklist;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.ivpds.analysis.AnalysisTestSupport;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

/**
 * Users reporting scam numbers and administrators reviewing the reports, over real HTTP against the real
 * application, PostgreSQL and MinIO. The AI service is not involved.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT, properties = {
        "ivpds.bootstrap.admin.email=admin@reports.test",
        "ivpds.bootstrap.admin.password=admin-password-1",
})
@Import({TestcontainersConfig.class, MinioConfig.class})
class BlacklistReportIntegrationTest extends AnalysisTestSupport {

    private static final String REPORTS = "/api/v1/blacklist/reports";
    private static final String ADMIN_REPORTS = "/api/v1/admin/blacklist/reports";

    // ------------------------------------------------------------------- users

    @Test
    void aUserReportsANumberInAnyFormatAndSeesOnlyTheirOwnReports() {
        Session user = register("reporter");
        Session other = register("reporter-other");

        ResponseEntity<JsonNode> created = report(user, Map.of("phoneNumber", "0941 000 001", "reason",
                "  Tự xưng công an, đòi chuyển tiền  "));

        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        JsonNode body = created.getBody();
        assertThat(body.get("phoneNumber").asText()).isEqualTo("+84941000001");
        assertThat(body.get("reason").asText()).isEqualTo("Tự xưng công an, đòi chuyển tiền");
        assertThat(body.get("status").asText()).isEqualTo("PENDING");
        assertThat(body.get("callId").isNull()).isTrue();
        assertThat(body.get("reviewedAt").isNull()).isTrue();
        // The answer does not say who reviews or who else reported the number.
        assertThat(body.has("reporterId")).isFalse();
        assertThat(body.has("reportsForNumber")).isFalse();

        // A report alone does not blacklist anything.
        assertThat(lookup(user, "0941000001").get("blacklisted").asBoolean()).isFalse();

        // The same number again, however it is typed, is refused; another user may still report it.
        assertError(report(user, Map.of("phoneNumber", "+84941000001")), HttpStatus.CONFLICT, "NUMBER_ALREADY_REPORTED");
        assertThat(report(other, Map.of("phoneNumber", "84941000001")).getStatusCode()).isEqualTo(HttpStatus.CREATED);
        report(user, Map.of("phoneNumber", "0941000002"));

        JsonNode mine = get(user, REPORTS).getBody();
        assertThat(mine.get("totalItems").asInt()).isEqualTo(2);
        assertThat(mine.get("items")).extracting(item -> item.get("phoneNumber").asText())
                .containsExactly("+84941000002", "+84941000001");
        assertThat(get(other, REPORTS).getBody().get("totalItems").asInt()).isEqualTo(1);
        assertThat(get(user, REPORTS + "?size=1&page=1").getBody().get("items").get(0).get("phoneNumber").asText())
                .isEqualTo("+84941000001");
    }

    @Test
    void aReportCanPointAtOneOfTheUsersOwnCallsAndTakesItsCallerNumber() {
        Session user = register("call-reporter");
        Session other = register("call-stranger");
        UUID withNumber = uploadCall(user, wav(1), "0942 000 001");
        UUID withoutNumber = uploadCall(user, wav(1));

        JsonNode fromCall = report(user, Map.of("callId", withNumber)).getBody();

        assertThat(fromCall.get("phoneNumber").asText()).isEqualTo("+84942000001");
        assertThat(fromCall.get("callId").asText()).isEqualTo(withNumber.toString());
        // Someone else's call is not found, a call without a caller number needs the number spelled out,
        // and a number that is not the caller of that call is refused.
        assertError(report(other, Map.of("callId", withNumber)), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(report(user, Map.of("callId", UUID.randomUUID())), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(report(user, Map.of("callId", withoutNumber)), HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");
        assertError(report(user, Map.of("callId", withNumber, "phoneNumber", "0942000009")), HttpStatus.BAD_REQUEST,
                "PHONE_NUMBER_MISMATCH");
        assertThat(report(user, Map.of("callId", withoutNumber, "phoneNumber", "0942000002")).getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        // Deleting the call keeps the report, without the link.
        assertThat(send(user, HttpMethod.DELETE, "/api/v1/calls/" + withNumber, null).getStatusCode())
                .isEqualTo(HttpStatus.NO_CONTENT);
        JsonNode kept = get(user, REPORTS).getBody().get("items").get(1);
        assertThat(kept.get("phoneNumber").asText()).isEqualTo("+84942000001");
        assertThat(kept.get("callId").isNull()).isTrue();
    }

    @Test
    void badReportsAreRefused() {
        Session user = register("bad-reporter");
        Session admin = admin();
        send(admin, HttpMethod.POST, "/api/v1/admin/blacklist", Map.of("phoneNumber", "0943000001"));

        assertThat(report(Session.ANONYMOUS, Map.of("phoneNumber", "0943000002")).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get(Session.ANONYMOUS, REPORTS).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertError(report(user, Map.of()), HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");
        assertError(report(user, Map.of("phoneNumber", "not a number")), HttpStatus.BAD_REQUEST,
                "INVALID_PHONE_NUMBER");
        assertError(report(user, Map.of("phoneNumber", "0943000003", "reason", "x".repeat(1001))),
                HttpStatus.BAD_REQUEST, "VALIDATION_FAILED");
        // A number that is already blocked needs no report.
        assertError(report(user, Map.of("phoneNumber", "0943 000 001")), HttpStatus.CONFLICT,
                "PHONE_NUMBER_ALREADY_BLACKLISTED");
        assertThat(get(user, REPORTS).getBody().get("totalItems").asInt()).isZero();
    }

    @Test
    void oneAccountCannotFloodTheReviewQueue() {
        Session user = register("flood");
        for (int i = 0; i < BlacklistReportService.MAX_PENDING_PER_USER; i++) {
            assertThat(report(user, Map.of("phoneNumber", "09440001%02d".formatted(i))).getStatusCode())
                    .isEqualTo(HttpStatus.CREATED);
        }

        assertError(report(user, Map.of("phoneNumber", "0944000199")), HttpStatus.TOO_MANY_REQUESTS,
                "TOO_MANY_PENDING_REPORTS");

        // Once one of them is reviewed, there is room again.
        String first = get(user, REPORTS + "?size=1").getBody().get("items").get(0).get("id").asText();
        assertThat(send(admin(), HttpMethod.POST, ADMIN_REPORTS + "/" + first + "/reject", null).getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(report(user, Map.of("phoneNumber", "0944000199")).getStatusCode()).isEqualTo(HttpStatus.CREATED);
    }

    // ------------------------------------------------------------------ admins

    @Test
    void theReviewQueueIsForAdministratorsOnly() {
        Session user = register("not-admin");
        String id = report(user, Map.of("phoneNumber", "0945000001")).getBody().get("id").asText();

        Map<String, HttpMethod> endpoints = new HashMap<>();
        endpoints.put(ADMIN_REPORTS, HttpMethod.GET);
        endpoints.put(ADMIN_REPORTS + "/" + id + "/approve", HttpMethod.POST);
        endpoints.put(ADMIN_REPORTS + "/" + id + "/reject", HttpMethod.POST);
        endpoints.forEach((path, method) -> {
            assertThat(send(user, method, path, null).getStatusCode()).as(path).isEqualTo(HttpStatus.FORBIDDEN);
            assertThat(send(Session.ANONYMOUS, method, path, null).getStatusCode()).as(path)
                    .isEqualTo(HttpStatus.UNAUTHORIZED);
        });
        assertThat(get(user, REPORTS).getBody().get("items").get(0).get("status").asText()).isEqualTo("PENDING");
    }

    @Test
    void approvingAReportBlacklistsTheNumberAndSettlesEveryPendingReportOfIt() {
        Session admin = admin();
        Session first = register("approve-a");
        Session second = register("approve-b");
        Session third = register("approve-c");
        String firstId = report(first, Map.of("phoneNumber", "0946000001", "reason", "Giả danh ngân hàng"))
                .getBody().get("id").asText();
        String secondId = report(second, Map.of("phoneNumber", "0946000001")).getBody().get("id").asText();
        String otherNumber = report(third, Map.of("phoneNumber", "0946000002")).getBody().get("id").asText();

        // The queue shows how many users reported each number.
        JsonNode queue = send(admin, HttpMethod.GET, ADMIN_REPORTS + "?status=PENDING&query=0946 000", null).getBody();
        assertThat(queue.get("totalItems").asInt()).isEqualTo(3);
        JsonNode newest = queue.get("items").get(0);
        assertThat(newest.get("id").asText()).isEqualTo(otherNumber);
        assertThat(newest.get("reportsForNumber").asInt()).isEqualTo(1);
        assertThat(newest.get("reporterId").asText()).isEqualTo(third.id().toString());
        assertThat(queue.get("items").get(1).get("reportsForNumber").asInt()).isEqualTo(2);
        assertThat(queue.get("items").get(1).get("blacklisted").asBoolean()).isFalse();

        ResponseEntity<JsonNode> approved = send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + secondId + "/approve",
                null);

        assertThat(approved.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(approved.getBody().get("status").asText()).isEqualTo("APPROVED");
        assertThat(approved.getBody().get("reviewedBy").asText()).isEqualTo(admin.id().toString());
        assertThat(approved.getBody().get("reviewedAt").isNull()).isFalse();
        assertThat(approved.getBody().get("blacklisted").asBoolean()).isTrue();
        // The number is blocked for everyone; the approved report had no reason, so the entry has none.
        JsonNode found = lookup(third, "0946000001");
        assertThat(found.get("blacklisted").asBoolean()).isTrue();
        assertThat(found.get("reason").isNull()).isTrue();
        // Both reports of that number are settled, the report of the other number is untouched.
        assertThat(statuses(first)).containsExactly("APPROVED");
        assertThat(statuses(second)).containsExactly("APPROVED");
        assertThat(statuses(third)).containsExactly("PENDING");
        assertThat(get(first, REPORTS).getBody().get("items").get(0).get("reviewedAt").isNull()).isFalse();
        assertThat(ids(send(admin, HttpMethod.GET, ADMIN_REPORTS + "?status=APPROVED&query=0946000001", null)
                .getBody())).containsExactlyInAnyOrder(firstId, secondId);

        // A reviewed report cannot be reviewed again, and an unknown one is not found.
        assertError(send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + firstId + "/reject", null),
                HttpStatus.CONFLICT, "REPORT_ALREADY_REVIEWED");
        assertError(send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + secondId + "/approve", null),
                HttpStatus.CONFLICT, "REPORT_ALREADY_REVIEWED");
        assertError(send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + UUID.randomUUID() + "/approve", null),
                HttpStatus.NOT_FOUND, "BLACKLIST_REPORT_NOT_FOUND");
        assertError(send(admin, HttpMethod.GET, ADMIN_REPORTS + "?status=MAYBE", null), HttpStatus.BAD_REQUEST,
                "BAD_REQUEST");

        // A call from the number now warns its receiver, as for any blacklisted number.
        UUID callId = uploadCall(third, wav(1), "0946000001");
        JsonNode notification = get(third, "/api/v1/notifications").getBody().get("items").get(0);
        assertThat(notification.get("type").asText()).isEqualTo("BLACKLISTED_CALLER");
        assertThat(notification.get("callId").asText()).isEqualTo(callId.toString());
    }

    @Test
    void theAdministratorCanGiveTheReasonShownToUsersAndApprovalReactivatesARemovedNumber() {
        Session admin = admin();
        Session user = register("reason");
        String entryId = send(admin, HttpMethod.POST, "/api/v1/admin/blacklist",
                Map.of("phoneNumber", "0947000001", "reason", "Lý do cũ")).getBody().get("id").asText();
        send(admin, HttpMethod.PATCH, "/api/v1/admin/blacklist/" + entryId, Map.of("active", false));
        String reportId = report(user, Map.of("phoneNumber", "0947000001", "reason", "lời của người dùng"))
                .getBody().get("id").asText();

        assertError(send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + reportId + "/approve",
                Map.of("reason", "x".repeat(1001))), HttpStatus.BAD_REQUEST, "VALIDATION_FAILED");
        ResponseEntity<JsonNode> approved = send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + reportId + "/approve",
                Map.of("reason", "Giả danh điện lực, đã xác minh"));

        assertThat(approved.getStatusCode()).isEqualTo(HttpStatus.OK);
        JsonNode found = lookup(user, "0947000001");
        assertThat(found.get("blacklisted").asBoolean()).isTrue();
        assertThat(found.get("reason").asText()).isEqualTo("Giả danh điện lực, đã xác minh");
        // The same entry was switched back on; no second row was created.
        assertThat(jdbc.queryForObject("select count(*) from blacklist_numbers where phone_number = '+84947000001'",
                Integer.class)).isEqualTo(1);

        // With no reason from the administrator, a new entry takes the reporter's reason.
        String second = report(user, Map.of("phoneNumber", "0947000002", "reason", "Dụ đầu tư tiền ảo"))
                .getBody().get("id").asText();
        send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + second + "/approve", Map.of());
        assertThat(lookup(user, "0947000002").get("reason").asText()).isEqualTo("Dụ đầu tư tiền ảo");
    }

    @Test
    void rejectingAReportLeavesTheNumberAndTheOtherReportsAlone() {
        Session admin = admin();
        Session first = register("reject-a");
        Session second = register("reject-b");
        String firstId = report(first, Map.of("phoneNumber", "0948000001")).getBody().get("id").asText();
        report(second, Map.of("phoneNumber", "0948000001"));

        ResponseEntity<JsonNode> rejected = send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + firstId + "/reject",
                null);

        assertThat(rejected.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(rejected.getBody().get("status").asText()).isEqualTo("REJECTED");
        assertThat(rejected.getBody().get("reviewedBy").asText()).isEqualTo(admin.id().toString());
        assertThat(rejected.getBody().get("blacklisted").asBoolean()).isFalse();
        assertThat(rejected.getBody().get("reportsForNumber").asInt()).isEqualTo(2);
        assertThat(lookup(first, "0948000001").get("blacklisted").asBoolean()).isFalse();
        assertThat(statuses(first)).containsExactly("REJECTED");
        assertThat(statuses(second)).containsExactly("PENDING");
        // The decision stands: the same user cannot report the same number again.
        assertError(report(first, Map.of("phoneNumber", "0948000001")), HttpStatus.CONFLICT, "NUMBER_ALREADY_REPORTED");
    }

    @Test
    void statisticsCountReportsByStatus() {
        Session admin = admin();
        Session user = register("report-stats");
        report(user, Map.of("phoneNumber", "0949000001"));
        String rejected = report(user, Map.of("phoneNumber", "0949000002")).getBody().get("id").asText();
        send(admin, HttpMethod.POST, ADMIN_REPORTS + "/" + rejected + "/reject", null);

        JsonNode counts = send(admin, HttpMethod.GET, "/api/v1/admin/statistics", null).getBody()
                .get("blacklistReports");

        for (String status : List.of("PENDING", "APPROVED", "REJECTED")) {
            assertThat(counts.get(status).asLong()).as(status).isEqualTo(jdbc.queryForObject(
                    "select count(*) from blacklist_reports where status = ?", Long.class, status));
        }
        assertThat(counts.get("PENDING").asLong()).isGreaterThanOrEqualTo(1);
        assertThat(counts.get("REJECTED").asLong()).isGreaterThanOrEqualTo(1);
    }

    // ----------------------------------------------------------------- helpers

    private Session admin() {
        return login("admin@reports.test", "admin-password-1");
    }

    private ResponseEntity<JsonNode> report(Session user, Map<String, ?> body) {
        return send(user, HttpMethod.POST, REPORTS, body);
    }

    private JsonNode lookup(Session user, String phoneNumber) {
        return rest.exchange("/api/v1/blacklist/lookup?phoneNumber={number}", HttpMethod.GET,
                new org.springframework.http.HttpEntity<>(bearer(user)), JsonNode.class, phoneNumber).getBody();
    }

    private List<String> statuses(Session user) {
        List<String> statuses = new ArrayList<>();
        get(user, REPORTS).getBody().get("items").forEach(item -> statuses.add(item.get("status").asText()));
        return statuses;
    }

    private static List<String> ids(JsonNode page) {
        List<String> ids = new ArrayList<>();
        page.get("items").forEach(item -> ids.add(item.get("id").asText()));
        return ids;
    }
}
