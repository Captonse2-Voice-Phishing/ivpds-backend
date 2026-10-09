package com.ivpds.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.ivpds.MailpitConfig;
import com.ivpds.MailpitContainer;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * End-to-end auth tests over real HTTP against the real application, a real PostgreSQL and a real
 * SMTP server. Nothing is mocked.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT, properties = {
        "ivpds.bootstrap.admin.email=Admin@Ivpds.Test",
        "ivpds.bootstrap.admin.password=" + AuthFlowIntegrationTest.ADMIN_PASSWORD,
})
@Import({TestcontainersConfig.class, MailpitConfig.class, MinioConfig.class,
        AuthFlowIntegrationTest.AdminProbeController.class})
class AuthFlowIntegrationTest {

    static final String ADMIN_PASSWORD = "admin-password-1";
    private static final String PASSWORD = "correct-horse-1";
    private static final Pattern SIX_DIGITS = Pattern.compile("\\b(\\d{6})\\b");

    @Autowired
    private TestRestTemplate rest;
    @Autowired
    private JdbcTemplate jdbc;
    @Autowired
    private JwtEncoder jwtEncoder;
    @Autowired
    private JwtProperties jwtProperties;
    @Autowired
    private MailpitContainer mailpit;
    @Autowired
    private AdminBootstrap adminBootstrap;

    // ---------------------------------------------------------------- register

    @Test
    void registerCreatesUserWithHashedPasswordAndReturnsWorkingTokens() {
        String email = uniqueEmail("register");

        ResponseEntity<JsonNode> response = post("/api/v1/auth/register",
                Map.of("email", email, "password", PASSWORD, "fullName", "Nguyễn Văn A", "phoneNumber", "0901234567"),
                null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        JsonNode body = response.getBody();
        assertThat(body.get("tokenType").asText()).isEqualTo("Bearer");
        assertThat(body.get("expiresIn").asLong()).isEqualTo(900);
        assertThat(body.get("refreshToken").asText()).isNotBlank();
        assertThat(body.get("user").get("email").asText()).isEqualTo(email);
        assertThat(rolesOf(body.get("user"))).containsExactly("USER");

        String storedHash = jdbc.queryForObject("select password_hash from users where email = ?", String.class, email);
        assertThat(storedHash).startsWith("$2").doesNotContain(PASSWORD);

        ResponseEntity<JsonNode> me = get("/api/v1/users/me", body.get("accessToken").asText());
        assertThat(me.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(me.getBody().get("email").asText()).isEqualTo(email);
        assertThat(me.getBody().get("fullName").asText()).isEqualTo("Nguyễn Văn A");
        assertThat(me.getBody().get("blacklistAlertEnabled").asBoolean()).isTrue();
        assertThat(me.getBody().has("passwordHash")).isFalse();
    }

    @Test
    void registerRejectsDuplicateEmailIgnoringCase() {
        String email = uniqueEmail("dup");
        register(email);

        ResponseEntity<JsonNode> response = post("/api/v1/auth/register",
                Map.of("email", email.toUpperCase(), "password", PASSWORD, "fullName", "Someone Else"), null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(response.getBody().get("code").asText()).isEqualTo("EMAIL_ALREADY_REGISTERED");
    }

    @Test
    void registerValidatesInput() {
        ResponseEntity<JsonNode> response = post("/api/v1/auth/register",
                Map.of("email", "not-an-email", "password", "short", "fullName", "", "phoneNumber", "abc"), null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody().get("code").asText()).isEqualTo("VALIDATION_FAILED");
        assertThat(response.getBody().get("fieldErrors").findValuesAsText("field"))
                .contains("email", "password", "fullName", "phoneNumber");
    }

    @Test
    void registerCannotGrantAdminRole() {
        String email = uniqueEmail("escalate");

        ResponseEntity<JsonNode> response = post("/api/v1/auth/register",
                Map.of("email", email, "password", PASSWORD, "fullName", "Sneaky", "roles", List.of("ADMIN"),
                        "role", "ADMIN"), null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(rolesOf(response.getBody().get("user"))).containsExactly("USER");
        assertThat(get("/api/v1/admin/probe", response.getBody().get("accessToken").asText()).getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
    }

    // ------------------------------------------------------------------- login

    @Test
    void loginSucceedsWithCorrectCredentialsRegardlessOfEmailCase() {
        String email = uniqueEmail("login");
        register(email);

        ResponseEntity<JsonNode> response = login(email.toUpperCase(), PASSWORD);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(get("/api/v1/users/me", response.getBody().get("accessToken").asText()).getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }

    @Test
    void loginFailsTheSameWayForWrongPasswordAndUnknownEmail() {
        String email = uniqueEmail("badlogin");
        register(email);

        ResponseEntity<JsonNode> wrongPassword = login(email, "wrong-password");
        ResponseEntity<JsonNode> unknownEmail = login(uniqueEmail("nobody"), PASSWORD);

        assertThat(wrongPassword.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(unknownEmail.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(wrongPassword.getBody().get("code").asText()).isEqualTo("INVALID_CREDENTIALS");
        assertThat(unknownEmail.getBody().get("code").asText()).isEqualTo("INVALID_CREDENTIALS");
        assertThat(unknownEmail.getBody().get("message").asText())
                .isEqualTo(wrongPassword.getBody().get("message").asText());
    }

    @Test
    void lockedAccountCannotLoginOrRefresh() {
        String email = uniqueEmail("locked");
        String refreshToken = register(email).get("refreshToken").asText();
        jdbc.update("update users set status = 'LOCKED' where email = ?", email);

        ResponseEntity<JsonNode> loginResponse = login(email, PASSWORD);
        ResponseEntity<JsonNode> refreshResponse = refresh(refreshToken);

        assertThat(loginResponse.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(loginResponse.getBody().get("code").asText()).isEqualTo("ACCOUNT_LOCKED");
        assertThat(refreshResponse.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        // A wrong password on a locked account must not reveal that the account is locked.
        assertThat(login(email, "wrong-password").getBody().get("code").asText()).isEqualTo("INVALID_CREDENTIALS");
    }

    // ----------------------------------------------------------- access tokens

    @Test
    void protectedEndpointRejectsMissingAndMalformedTokens() {
        ResponseEntity<JsonNode> missing = get("/api/v1/users/me", null);
        ResponseEntity<JsonNode> garbage = get("/api/v1/users/me", "not.a.jwt");

        assertThat(missing.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(missing.getBody().get("code").asText()).isEqualTo("UNAUTHORIZED");
        assertThat(missing.getBody().get("path").asText()).isEqualTo("/api/v1/users/me");
        assertThat(missing.getBody().get("requestId").asText()).isEqualTo(missing.getHeaders().getFirst("X-Request-Id"));
        assertThat(garbage.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void expiredAccessTokenIsRejected() {
        String userId = register(uniqueEmail("expired")).get("user").get("id").asText();
        Instant now = Instant.now();
        String stillValid = signedToken(jwtEncoder, jwtProperties.issuer(), userId, now, now.plusSeconds(300));
        String expired = signedToken(jwtEncoder, jwtProperties.issuer(), userId, now.minusSeconds(3600),
                now.minusSeconds(600));

        assertThat(get("/api/v1/users/me", stillValid).getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(get("/api/v1/users/me", expired).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void tokenSignedWithAnotherKeyOrIssuerIsRejected() {
        String userId = register(uniqueEmail("forged")).get("user").get("id").asText();
        Instant now = Instant.now();
        JwtEncoder attackerEncoder = new NimbusJwtEncoder(new ImmutableSecret<>(new SecretKeySpec(
                "attacker-secret-attacker-secret-attacker".getBytes(StandardCharsets.UTF_8), "HmacSHA256")));
        String forged = signedToken(attackerEncoder, jwtProperties.issuer(), userId, now, now.plusSeconds(300));
        String wrongIssuer = signedToken(jwtEncoder, "someone-else", userId, now, now.plusSeconds(300));

        assertThat(get("/api/v1/users/me", forged).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get("/api/v1/users/me", wrongIssuer).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    // ---------------------------------------------------------- refresh tokens

    @Test
    void refreshRotatesTheTokenPair() {
        JsonNode first = register(uniqueEmail("refresh"));
        String firstRefresh = first.get("refreshToken").asText();

        ResponseEntity<JsonNode> response = refresh(firstRefresh);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        String secondRefresh = response.getBody().get("refreshToken").asText();
        assertThat(secondRefresh).isNotEqualTo(firstRefresh);
        assertThat(get("/api/v1/users/me", response.getBody().get("accessToken").asText()).getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(refresh(secondRefresh).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void refreshTokenIsStoredOnlyAsHash() {
        JsonNode body = register(uniqueEmail("hash"));
        String refreshToken = body.get("refreshToken").asText();
        UUID userId = UUID.fromString(body.get("user").get("id").asText());

        List<String> stored = jdbc.queryForList("select token_hash from refresh_tokens where user_id = ?",
                String.class, userId);

        assertThat(stored).hasSize(1);
        assertThat(stored.get(0)).hasSize(64).isNotEqualTo(refreshToken).doesNotContain(refreshToken);
    }

    @Test
    void reusingARotatedRefreshTokenRevokesEverySessionOfTheUser() {
        String firstRefresh = register(uniqueEmail("reuse")).get("refreshToken").asText();
        String secondRefresh = refresh(firstRefresh).getBody().get("refreshToken").asText();

        ResponseEntity<JsonNode> replay = refresh(firstRefresh);

        assertThat(replay.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(replay.getBody().get("code").asText()).isEqualTo("INVALID_REFRESH_TOKEN");
        assertThat(refresh(secondRefresh).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void expiredAndUnknownRefreshTokensAreRejected() {
        JsonNode body = register(uniqueEmail("refresh-expired"));
        jdbc.update("update refresh_tokens set expires_at = now() - interval '1 minute' where user_id = ?",
                UUID.fromString(body.get("user").get("id").asText()));

        assertThat(refresh(body.get("refreshToken").asText()).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(refresh("this-token-was-never-issued").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void logoutRevokesTheRefreshTokenAndIsIdempotent() {
        String refreshToken = register(uniqueEmail("logout")).get("refreshToken").asText();

        ResponseEntity<JsonNode> first = post("/api/v1/auth/logout", Map.of("refreshToken", refreshToken), null);
        ResponseEntity<JsonNode> second = post("/api/v1/auth/logout", Map.of("refreshToken", refreshToken), null);

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(second.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(refresh(refreshToken).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    // ------------------------------------------------------------------- roles

    @Test
    void adminEndpointsAreForbiddenForUsersAndAllowedForAdmins() {
        String userToken = register(uniqueEmail("plain")).get("accessToken").asText();
        ResponseEntity<JsonNode> adminLogin = login("admin@ivpds.test", ADMIN_PASSWORD);
        assertThat(adminLogin.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(rolesOf(adminLogin.getBody().get("user"))).containsExactly("ADMIN");

        ResponseEntity<JsonNode> anonymous = get("/api/v1/admin/probe", null);
        ResponseEntity<JsonNode> asUser = get("/api/v1/admin/probe", userToken);
        ResponseEntity<JsonNode> asAdmin = get("/api/v1/admin/probe", adminLogin.getBody().get("accessToken").asText());

        assertThat(anonymous.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(asUser.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(asUser.getBody().get("code").asText()).isEqualTo("FORBIDDEN");
        assertThat(asAdmin.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(asAdmin.getBody().get("ok").asBoolean()).isTrue();
    }

    @Test
    void adminBootstrapIsIdempotentAndKeepsTheExistingPassword() {
        adminBootstrap.run(null);
        adminBootstrap.run(null);

        assertThat(jdbc.queryForObject("select count(*) from users where email = 'admin@ivpds.test'", Integer.class))
                .isEqualTo(1);
        assertThat(login("admin@ivpds.test", ADMIN_PASSWORD).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    // --------------------------------------------------------- change password

    @Test
    void changePasswordRequiresTheCurrentPassword() {
        String email = uniqueEmail("change-wrong");
        String accessToken = register(email).get("accessToken").asText();

        ResponseEntity<JsonNode> response = post("/api/v1/auth/change-password",
                Map.of("currentPassword", "not-my-password", "newPassword", "brand-new-pass-2"), accessToken);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody().get("code").asText()).isEqualTo("INVALID_CURRENT_PASSWORD");
        assertThat(login(email, PASSWORD).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void changePasswordRequiresAuthentication() {
        ResponseEntity<JsonNode> response = post("/api/v1/auth/change-password",
                Map.of("currentPassword", PASSWORD, "newPassword", "brand-new-pass-2"), null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void changePasswordReplacesThePasswordAndSignsOutOtherSessions() {
        String email = uniqueEmail("change");
        JsonNode session = register(email);

        ResponseEntity<JsonNode> response = post("/api/v1/auth/change-password",
                Map.of("currentPassword", PASSWORD, "newPassword", "brand-new-pass-2"),
                session.get("accessToken").asText());

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(login(email, PASSWORD).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(login(email, "brand-new-pass-2").getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(refresh(session.get("refreshToken").asText()).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    // ---------------------------------------------------------- password reset

    @Test
    void forgotPasswordEmailsACodeThatResetsThePasswordOnce() {
        String email = uniqueEmail("reset");
        String oldRefresh = register(email).get("refreshToken").asText();

        ResponseEntity<JsonNode> forgot = post("/api/v1/auth/forgot-password", Map.of("email", email), null);

        assertThat(forgot.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        String code = awaitResetCode(email);
        String storedHash = jdbc.queryForObject("select t.code_hash from password_reset_tokens t"
                + " join users u on u.id = t.user_id where u.email = ?", String.class, email);
        assertThat(storedHash).doesNotContain(code);

        ResponseEntity<JsonNode> reset = resetPassword(email, code, "after-reset-pass-3");

        assertThat(reset.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(login(email, PASSWORD).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(login(email, "after-reset-pass-3").getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(refresh(oldRefresh).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        // The code is single-use.
        assertThat(resetPassword(email, code, "another-pass-4").getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(login(email, "after-reset-pass-3").getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void forgotPasswordForUnknownEmailLooksTheSameAndSendsNothing() {
        String email = uniqueEmail("ghost");

        ResponseEntity<JsonNode> response = post("/api/v1/auth/forgot-password", Map.of("email", email), null);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(mailpit.messageTextsTo(email)).isEmpty();
    }

    @Test
    void forgotPasswordSendsAtMostOneEmailPerResendInterval() {
        String email = uniqueEmail("flood");
        register(email);

        post("/api/v1/auth/forgot-password", Map.of("email", email), null);
        awaitResetCode(email);
        ResponseEntity<JsonNode> second = post("/api/v1/auth/forgot-password", Map.of("email", email), null);

        assertThat(second.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        assertThat(mailpit.messageTextsTo(email)).hasSize(1);
    }

    @Test
    void wrongResetCodeIsRejectedAndCodeIsLockedAfterTooManyAttempts() {
        String email = uniqueEmail("guess");
        register(email);
        post("/api/v1/auth/forgot-password", Map.of("email", email), null);
        String code = awaitResetCode(email);
        String wrongCode = code.equals("000000") ? "000001" : "000000";

        for (int attempt = 1; attempt <= 5; attempt++) {
            ResponseEntity<JsonNode> response = resetPassword(email, wrongCode, "guessed-pass-5");
            assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
            assertThat(response.getBody().get("code").asText()).isEqualTo("INVALID_RESET_CODE");
        }

        assertThat(jdbc.queryForObject("select t.attempts from password_reset_tokens t"
                + " join users u on u.id = t.user_id where u.email = ?", Integer.class, email)).isEqualTo(5);
        // Even the correct code no longer works once the attempts are used up.
        assertThat(resetPassword(email, code, "guessed-pass-5").getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(login(email, PASSWORD).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void expiredResetCodeIsRejected() {
        String email = uniqueEmail("late");
        register(email);
        post("/api/v1/auth/forgot-password", Map.of("email", email), null);
        String code = awaitResetCode(email);
        jdbc.update("update password_reset_tokens set expires_at = now() - interval '1 minute'"
                + " where user_id = (select id from users where email = ?)", email);

        assertThat(resetPassword(email, code, "too-late-pass-6").getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(login(email, PASSWORD).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    // ----------------------------------------------------------------- helpers

    @RestController
    static class AdminProbeController {

        @GetMapping("/api/v1/admin/probe")
        Map<String, Boolean> probe() {
            return Map.of("ok", true);
        }
    }

    private static String uniqueEmail(String prefix) {
        return prefix + "-" + UUID.randomUUID() + "@example.com";
    }

    private static List<String> rolesOf(JsonNode user) {
        List<String> roles = new ArrayList<>();
        user.get("roles").forEach(role -> roles.add(role.asText()));
        return roles;
    }

    private JsonNode register(String email) {
        ResponseEntity<JsonNode> response = post("/api/v1/auth/register",
                Map.of("email", email, "password", PASSWORD, "fullName", "Test User"), null);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        return response.getBody();
    }

    private ResponseEntity<JsonNode> login(String email, String password) {
        return post("/api/v1/auth/login", Map.of("email", email, "password", password), null);
    }

    private ResponseEntity<JsonNode> refresh(String refreshToken) {
        return post("/api/v1/auth/refresh", Map.of("refreshToken", refreshToken), null);
    }

    private ResponseEntity<JsonNode> resetPassword(String email, String code, String newPassword) {
        return post("/api/v1/auth/reset-password",
                Map.of("email", email, "code", code, "newPassword", newPassword), null);
    }

    private ResponseEntity<JsonNode> post(String path, Object body, String bearerToken) {
        return rest.exchange(path, HttpMethod.POST, new HttpEntity<>(body, headers(bearerToken)), JsonNode.class);
    }

    private ResponseEntity<JsonNode> get(String path, String bearerToken) {
        return rest.exchange(path, HttpMethod.GET, new HttpEntity<>(headers(bearerToken)), JsonNode.class);
    }

    private static HttpHeaders headers(String bearerToken) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        if (bearerToken != null) {
            headers.setBearerAuth(bearerToken);
        }
        return headers;
    }

    private static String signedToken(JwtEncoder encoder, String issuer, String subject, Instant issuedAt,
            Instant expiresAt) {
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .subject(subject)
                .issuedAt(issuedAt)
                .expiresAt(expiresAt)
                .claim("roles", List.of("USER"))
                .build();
        return encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims))
                .getTokenValue();
    }

    /** Reads the 6-digit code from the email that the SMTP server actually received. */
    private String awaitResetCode(String email) {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(5));
        while (true) {
            List<String> texts = mailpit.messageTextsTo(email);
            if (!texts.isEmpty()) {
                Matcher matcher = SIX_DIGITS.matcher(texts.get(0));
                assertThat(matcher.find()).as("reset email contains a 6-digit code: %s", texts.get(0)).isTrue();
                return matcher.group(1);
            }
            assertThat(Instant.now()).as("reset email for %s arrived in time", email).isBefore(deadline);
            try {
                Thread.sleep(100);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        }
    }
}
