package com.ivpds;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase.Replace;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Runs the real Flyway migrations against a real PostgreSQL and checks the resulting schema:
 * tables, seed data, and that the constraints reject bad data. Each test rolls back.
 */
@JdbcTest
@AutoConfigureTestDatabase(replace = Replace.NONE)
@Import(TestcontainersConfig.class)
class SchemaMigrationTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void allMigrationsAreAppliedSuccessfully() {
        List<String> versions = jdbc.queryForList(
                "select version from flyway_schema_history where success order by installed_rank", String.class);
        Integer failed = jdbc.queryForObject(
                "select count(*) from flyway_schema_history where not success", Integer.class);

        assertThat(versions).containsExactly("1", "2", "3", "4", "5", "6", "7", "8");
        assertThat(failed).isZero();
    }

    @Test
    void allExpectedTablesExist() {
        List<String> tables = jdbc.queryForList(
                "select table_name from information_schema.tables where table_schema = 'public'", String.class);

        assertThat(tables).containsExactlyInAnyOrder(
                "users", "roles", "user_roles", "refresh_tokens", "password_reset_tokens",
                "call_records", "audio_files", "transcripts", "analyses", "risk_results", "risk_indicators",
                "phishing_patterns", "blacklist_numbers", "notifications",
                "flyway_schema_history");
    }

    @Test
    void rolesAreSeeded() {
        List<String> roles = jdbc.queryForList("select name from roles", String.class);

        assertThat(roles).containsExactlyInAnyOrder("USER", "ADMIN");
    }

    @Test
    void newUserGetsDefaults() {
        UUID user = insertUser("defaults@example.com");

        assertThat(jdbc.queryForObject("select status from users where id = ?", String.class, user))
                .isEqualTo("ACTIVE");
        assertThat(jdbc.queryForObject("select blacklist_alert_enabled from users where id = ?", Boolean.class, user))
                .isTrue();
    }

    @Test
    void emailIsUniqueIgnoringCase() {
        insertUser("someone@example.com");

        assertRejected("uq_users_email", () -> insertUser("SomeOne@Example.com"));
    }

    @Test
    void unknownUserStatusIsRejected() {
        UUID user = insertUser("status@example.com");

        assertRejected("ck_users_status",
                () -> jdbc.update("update users set status = 'DELETED' where id = ?", user));
    }

    @Test
    void userCanHoldARoleOnlyOnce() {
        UUID user = insertUser("roles@example.com");
        String grant = "insert into user_roles (user_id, role_id) select ?, id from roles where name = 'USER'";
        jdbc.update(grant, user);

        assertRejected("pk_user_roles", () -> jdbc.update(grant, user));
    }

    @Test
    void refreshTokenHashIsUnique() {
        UUID user = insertUser("tokens@example.com");
        String hash = "a".repeat(64);
        String insert = "insert into refresh_tokens (user_id, token_hash, expires_at) values (?, ?, now() + interval '7 days')";
        jdbc.update(insert, user, hash);

        assertRejected("uq_refresh_tokens_token_hash", () -> jdbc.update(insert, user, hash));
    }

    @Test
    void callRecordRequiresAnExistingUser() {
        assertRejected("fk_call_records_user", () -> jdbc.update(
                "insert into call_records (user_id, source) values (?, 'UPLOADED')", UUID.randomUUID()));
    }

    @Test
    void callRecordSourceAndCallerNumberAreValidated() {
        UUID user = insertUser("calls@example.com");

        assertRejected("ck_call_records_source", () -> jdbc.update(
                "insert into call_records (user_id, source) values (?, 'STREAMED')", user));
        assertRejected("ck_call_records_caller_number", () -> jdbc.update(
                "insert into call_records (user_id, source, caller_number) values (?, 'UPLOADED', '09-12 abc')", user));
    }

    @Test
    void callerNumberIsOptional() {
        UUID user = insertUser("hidden@example.com");

        UUID call = insertCall(user);

        assertThat(jdbc.queryForObject("select caller_number from call_records where id = ?", String.class, call))
                .isNull();
    }

    @Test
    void audioFileMustHavePositiveSize() {
        UUID call = insertCall(insertUser("audio-size@example.com"));

        assertRejected("ck_audio_files_size", () -> jdbc.update(
                "insert into audio_files (call_record_id, bucket, object_key, content_type, size_bytes)"
                        + " values (?, 'b', 'k', 'audio/mpeg', 0)", call));
    }

    @Test
    void sameStorageObjectCannotBeRegisteredTwice() {
        UUID user = insertUser("audio-dup@example.com");
        String insert = "insert into audio_files (call_record_id, bucket, object_key, content_type, size_bytes)"
                + " values (?, 'ivpds-audio', 'calls/a.mp3', 'audio/mpeg', 10)";
        jdbc.update(insert, insertCall(user));

        assertRejected("uq_audio_files_object", () -> jdbc.update(insert, insertCall(user)));
    }

    @Test
    void analysisStatusIsValidatedAndDefaultsToPending() {
        UUID call = insertCall(insertUser("analysis@example.com"));
        UUID analysis = insertAnalysis(call);

        assertThat(jdbc.queryForObject("select status from analyses where id = ?", String.class, analysis))
                .isEqualTo("PENDING");
        assertRejected("ck_analyses_status",
                () -> jdbc.update("update analyses set status = 'DONE' where id = ?", analysis));
    }

    @Test
    void analysisHasAtMostOneTranscriptAndStoresVietnameseText() {
        UUID analysis = insertAnalysis(insertCall(insertUser("transcript@example.com")));
        String text = "Anh đọc mã OTP tôi vừa gửi.";
        String insert = "insert into transcripts (analysis_id, content) values (?, ?)";
        jdbc.update(insert, analysis, text);

        assertThat(jdbc.queryForObject("select content from transcripts where analysis_id = ?", String.class, analysis))
                .isEqualTo(text);
        assertThat(jdbc.queryForObject("select language from transcripts where analysis_id = ?", String.class, analysis))
                .isEqualTo("vi");
        assertRejected("uq_transcripts_analysis", () -> jdbc.update(insert, analysis, "again"));
    }

    @Test
    void riskScoreMustBeBetween0And100() {
        UUID analysis = insertAnalysis(insertCall(insertUser("score@example.com")));

        assertRejected("ck_risk_results_score", () -> insertRisk(analysis, 101, "HIGH", "0.9"));
        assertRejected("ck_risk_results_score", () -> insertRisk(analysis, -1, "LOW", "0.9"));
    }

    @Test
    void riskLevelMustBeLowMediumOrHigh() {
        UUID analysis = insertAnalysis(insertCall(insertUser("level@example.com")));

        assertRejected("ck_risk_results_level", () -> insertRisk(analysis, 50, "CRITICAL", "0.9"));
    }

    @Test
    void confidenceMustBeBetween0And1() {
        UUID analysis = insertAnalysis(insertCall(insertUser("confidence@example.com")));

        assertRejected("ck_risk_results_confidence", () -> insertRisk(analysis, 50, "MEDIUM", "1.5"));
    }

    @Test
    void riskResultAcceptsBoundaryValuesAndRejectsDuplicateIndicators() {
        UUID analysis = insertAnalysis(insertCall(insertUser("risk@example.com")));
        UUID risk = insertRisk(analysis, 100, "HIGH", "1.0");
        String addIndicator = "insert into risk_indicators (risk_result_id, indicator_code) values (?, ?)";
        jdbc.update(addIndicator, risk, "OTP_REQUEST");
        jdbc.update(addIndicator, risk, "BANK_IMPERSONATION");

        assertThat(jdbc.queryForObject("select count(*) from risk_indicators where risk_result_id = ?", Integer.class,
                risk)).isEqualTo(2);
        assertRejected("uq_risk_indicators_result_code", () -> jdbc.update(addIndicator, risk, "OTP_REQUEST"));
    }

    @Test
    void blacklistNumberIsUniqueAndValidated() {
        String insert = "insert into blacklist_numbers (phone_number) values (?)";
        jdbc.update(insert, "+84901234567");

        assertRejected("uq_blacklist_numbers_phone_number", () -> jdbc.update(insert, "+84901234567"));
        assertRejected("ck_blacklist_numbers_phone_number", () -> jdbc.update(insert, "not-a-number"));
    }

    @Test
    void deletingAUserRemovesTheirDataButKeepsSharedRecords() {
        UUID user = insertUser("leaving@example.com");
        UUID call = insertCall(user);
        jdbc.update("insert into audio_files (call_record_id, bucket, object_key, content_type, size_bytes)"
                + " values (?, 'ivpds-audio', 'calls/leaving.mp3', 'audio/mpeg', 10)", call);
        UUID analysis = insertAnalysis(call);
        jdbc.update("insert into transcripts (analysis_id, content) values (?, 'x')", analysis);
        UUID risk = insertRisk(analysis, 70, "HIGH", "0.8");
        jdbc.update("insert into risk_indicators (risk_result_id, indicator_code) values (?, 'URGENCY')", risk);
        jdbc.update("insert into notifications (user_id, type, title, message, analysis_id)"
                + " values (?, 'HIGH_RISK', 't', 'm', ?)", user, analysis);
        jdbc.update("insert into refresh_tokens (user_id, token_hash, expires_at) values (?, ?, now())", user,
                "b".repeat(64));
        jdbc.update("insert into password_reset_tokens (user_id, code_hash, expires_at) values (?, 'h', now())", user);
        jdbc.update("insert into blacklist_numbers (phone_number, created_by) values ('0900000001', ?)", user);
        jdbc.update("insert into phishing_patterns (name, indicator_code, pattern, created_by)"
                + " values ('n', 'OTP_REQUEST', 'p', ?)", user);

        jdbc.update("delete from users where id = ?", user);

        for (String table : List.of("call_records", "audio_files", "analyses", "transcripts", "risk_results",
                "risk_indicators", "notifications", "refresh_tokens", "password_reset_tokens")) {
            assertThat(jdbc.queryForObject("select count(*) from " + table, Integer.class)).as(table).isZero();
        }
        assertThat(jdbc.queryForObject(
                "select count(*) from blacklist_numbers where phone_number = '0900000001' and created_by is null",
                Integer.class)).isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "select count(*) from phishing_patterns where created_by is null", Integer.class)).isEqualTo(1);
    }

    private UUID insertUser(String email) {
        return jdbc.queryForObject(
                "insert into users (email, password_hash, full_name) values (?, 'x', 'Test User') returning id",
                UUID.class, email);
    }

    private UUID insertCall(UUID user) {
        return jdbc.queryForObject(
                "insert into call_records (user_id, source) values (?, 'UPLOADED') returning id", UUID.class, user);
    }

    private UUID insertAnalysis(UUID call) {
        return jdbc.queryForObject(
                "insert into analyses (call_record_id) values (?) returning id", UUID.class, call);
    }

    private UUID insertRisk(UUID analysis, int score, String level, String confidence) {
        return jdbc.queryForObject(
                "insert into risk_results (analysis_id, risk_score, risk_level, confidence)"
                        + " values (?, ?, ?, ?::numeric) returning id",
                UUID.class, analysis, score, level, confidence);
    }

    private void assertRejected(String constraint, Runnable statement) {
        // A failed statement aborts the surrounding PostgreSQL transaction, so each attempt runs
        // inside its own savepoint to keep the test transaction usable.
        jdbc.execute("savepoint attempt");
        assertThatThrownBy(statement::run)
                .isInstanceOf(DataIntegrityViolationException.class)
                .hasMessageContaining(constraint);
        jdbc.execute("rollback to savepoint attempt");
    }
}
