package com.ivpds.call;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.ivpds.MinioConfig;
import com.ivpds.TestcontainersConfig;
import com.ivpds.audio.StorageProperties;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
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
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.S3Object;

/**
 * Profile, call submission and audio storage over real HTTP against the real application, a real
 * PostgreSQL and a real MinIO. Nothing is mocked.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT, properties = {
        "spring.servlet.multipart.max-file-size=1MB",
        "spring.servlet.multipart.max-request-size=2MB",
})
@Import({TestcontainersConfig.class, MinioConfig.class})
class UserCallAudioIntegrationTest {

    private static final String PASSWORD = "correct-horse-1";

    @Autowired
    private TestRestTemplate rest;
    @Autowired
    private JdbcTemplate jdbc;
    @Autowired
    private S3Client s3;
    @Autowired
    private StorageProperties storage;

    // ------------------------------------------------------------------ bucket

    @Test
    void bucketIsCreatedAtStartup() {
        assertThat(s3.listBuckets().buckets()).extracting(b -> b.name()).contains(storage.bucket());
    }

    // ------------------------------------------------------------------ upload

    @Test
    void uploadStoresTheAudioInMinioAndOnlyMetadataInPostgres() throws Exception {
        Session user = register("upload");
        byte[] wav = wav(2);

        ResponseEntity<JsonNode> response = upload(user, "Cuộc gọi ngân hàng.wav", wav,
                Map.of("callerNumber", "090 123 4567", "calledAt", "2026-10-01T02:30:00Z", "source", "RECORDED"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        JsonNode body = response.getBody();
        assertThat(body.get("callerNumber").asText()).isEqualTo("+84901234567");
        assertThat(body.get("calledAt").asText()).isEqualTo("2026-10-01T02:30:00Z");
        assertThat(body.get("source").asText()).isEqualTo("RECORDED");
        JsonNode audio = body.get("audio");
        assertThat(audio.get("originalFilename").asText()).isEqualTo("Cuộc gọi ngân hàng.wav");
        assertThat(audio.get("contentType").asText()).isEqualTo("audio/wav");
        assertThat(audio.get("sizeBytes").asLong()).isEqualTo(wav.length);
        assertThat(audio.get("checksumSha256").asText()).isEqualTo(sha256(wav));
        // Storage location is internal.
        assertThat(body.toString()).doesNotContain("objectKey", "bucket", "calls/");

        Map<String, Object> row = jdbc.queryForMap(
                "select bucket, object_key, size_bytes, checksum_sha256 from audio_files where call_record_id = ?",
                UUID.fromString(body.get("id").asText()));
        String key = (String) row.get("object_key");
        assertThat(row.get("bucket")).isEqualTo(storage.bucket());
        assertThat(key).startsWith("calls/" + user.id + "/").endsWith(".wav").doesNotContain("ngân");
        assertThat(row.get("size_bytes")).isEqualTo((long) wav.length);

        byte[] stored = s3.getObjectAsBytes(b -> b.bucket(storage.bucket()).key(key)).asByteArray();
        assertThat(stored).isEqualTo(wav);
        // No column of audio_files can hold the audio itself.
        List<String> binaryColumns = jdbc.queryForList("select column_name from information_schema.columns"
                + " where table_name = 'audio_files' and data_type in ('bytea', 'oid')", String.class);
        assertThat(binaryColumns).isEmpty();
    }

    @Test
    void uploadWorksWithOnlyTheAudioPartAndWithOctetStreamContentType() {
        Session user = register("minimal");

        ResponseEntity<JsonNode> response = upload(user, "recording.wav", wav(1), Map.of(),
                MediaType.APPLICATION_OCTET_STREAM);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody().get("source").asText()).isEqualTo("UPLOADED");
        assertThat(response.getBody().get("callerNumber").isNull()).isTrue();
        assertThat(response.getBody().get("audio").get("contentType").asText()).isEqualTo("audio/wav");
    }

    // ---------------------------------------------------------------- download

    @Test
    void downloadReturnsExactlyTheUploadedBytes() {
        Session user = register("download");
        byte[] wav = wav(3);
        String callId = upload(user, "call.wav", wav, Map.of()).getBody().get("id").asText();

        ResponseEntity<byte[]> response = rest.exchange("/api/v1/calls/" + callId + "/audio", HttpMethod.GET,
                new HttpEntity<>(bearer(user)), byte[].class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo(wav);
        assertThat(response.getHeaders().getContentType()).isEqualTo(MediaType.parseMediaType("audio/wav"));
        assertThat(response.getHeaders().getContentLength()).isEqualTo(wav.length);
        assertThat(response.getHeaders().getContentDisposition().getFilename()).isEqualTo("call.wav");
    }

    @Test
    void downloadReportsAudioMissingFromStorageInsteadOfFailing() {
        Session user = register("missing-object");
        String callId = upload(user, "call.wav", wav(1), Map.of()).getBody().get("id").asText();
        String key = jdbc.queryForObject("select object_key from audio_files where call_record_id = ?", String.class,
                UUID.fromString(callId));
        s3.deleteObject(b -> b.bucket(storage.bucket()).key(key));

        ResponseEntity<JsonNode> response = get(user, "/api/v1/calls/" + callId + "/audio");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody().get("code").asText()).isEqualTo("AUDIO_OBJECT_MISSING");
        // The call itself is still readable.
        assertThat(get(user, "/api/v1/calls/" + callId).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    // ----------------------------------------------------------- invalid input

    @Test
    void invalidUploadsAreRejectedAndLeaveNothingBehind() {
        Session user = register("invalid");
        byte[] text = "This is a text file, not audio.".getBytes(StandardCharsets.UTF_8);

        ResponseEntity<JsonNode> wrongExtension = upload(user, "notes.txt", text, Map.of());
        ResponseEntity<JsonNode> renamedText = upload(user, "fake.mp3", text, Map.of());
        ResponseEntity<JsonNode> empty = upload(user, "empty.wav", new byte[0], Map.of());
        ResponseEntity<JsonNode> badCaller = upload(user, "call.wav", wav(1), Map.of("callerNumber", "abc"));
        ResponseEntity<JsonNode> badSource = upload(user, "call.wav", wav(1), Map.of("source", "STREAMED"));
        ResponseEntity<JsonNode> badTime = upload(user, "call.wav", wav(1), Map.of("calledAt", "yesterday"));
        ResponseEntity<JsonNode> noAudioPart = rest.exchange("/api/v1/calls", HttpMethod.POST,
                new HttpEntity<>(new LinkedMultiValueMap<>(Map.of("callerNumber", List.of("0901234567"))),
                        multipart(user)), JsonNode.class);

        assertError(wrongExtension, HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_AUDIO_FORMAT");
        assertError(renamedText, HttpStatus.UNSUPPORTED_MEDIA_TYPE, "INVALID_AUDIO_CONTENT");
        assertError(empty, HttpStatus.BAD_REQUEST, "EMPTY_AUDIO");
        assertError(badCaller, HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");
        assertError(badSource, HttpStatus.BAD_REQUEST, "BAD_REQUEST");
        assertError(badTime, HttpStatus.BAD_REQUEST, "BAD_REQUEST");
        assertError(noAudioPart, HttpStatus.BAD_REQUEST, "BAD_REQUEST");

        assertThat(jdbc.queryForObject("select count(*) from call_records where user_id = ?", Integer.class,
                user.id)).isZero();
        assertThat(objectsOf(user)).isEmpty();
    }

    @Test
    void uploadLargerThanTheLimitIsRejected() {
        Session user = register("too-large");
        // The limit is 1 MB in this test; 40 seconds of 16 kHz mono PCM is about 1.28 MB.
        byte[] tooLarge = wav(40);
        assertThat(tooLarge.length).isGreaterThan(1024 * 1024);

        ResponseEntity<JsonNode> response = upload(user, "long.wav", tooLarge, Map.of());

        assertError(response, HttpStatus.PAYLOAD_TOO_LARGE, "PAYLOAD_TOO_LARGE");
        assertThat(objectsOf(user)).isEmpty();
    }

    // ----------------------------------------------------------- authorization

    @Test
    void callsAndAudioAreOnlyVisibleToTheirOwner() {
        Session owner = register("owner");
        Session other = register("other");
        String callId = upload(owner, "private.wav", wav(1), Map.of()).getBody().get("id").asText();

        assertError(get(other, "/api/v1/calls/" + callId), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(get(other, "/api/v1/calls/" + callId + "/audio"), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertThat(get(other, "/api/v1/calls").getBody().get("totalItems").asInt()).isZero();
        assertThat(get(owner, "/api/v1/calls/" + callId).getStatusCode()).isEqualTo(HttpStatus.OK);
        // An id that does not exist looks exactly the same as someone else's call.
        assertError(get(other, "/api/v1/calls/" + UUID.randomUUID()), HttpStatus.NOT_FOUND, "CALL_NOT_FOUND");
        assertError(get(other, "/api/v1/calls/not-a-uuid"), HttpStatus.BAD_REQUEST, "BAD_REQUEST");
    }

    @Test
    void callEndpointsRequireAuthentication() {
        Session anonymous = Session.ANONYMOUS;
        String someId = UUID.randomUUID().toString();

        assertThat(upload(anonymous, "call.wav", wav(1), Map.of()).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get(anonymous, "/api/v1/calls").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get(anonymous, "/api/v1/calls/" + someId).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get(anonymous, "/api/v1/calls/" + someId + "/audio").getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    // -------------------------------------------------------------------- list

    @Test
    void listIsPagedNewestFirstAndIncludesAudioMetadata() {
        Session user = register("list");
        String first = upload(user, "1.wav", wav(1), Map.of()).getBody().get("id").asText();
        String second = upload(user, "2.wav", wav(1), Map.of()).getBody().get("id").asText();
        String third = upload(user, "3.wav", wav(1), Map.of()).getBody().get("id").asText();

        JsonNode pageOne = get(user, "/api/v1/calls?page=0&size=2").getBody();
        JsonNode pageTwo = get(user, "/api/v1/calls?page=1&size=2").getBody();

        assertThat(pageOne.get("totalItems").asInt()).isEqualTo(3);
        assertThat(pageOne.get("totalPages").asInt()).isEqualTo(2);
        assertThat(pageOne.get("items").findValuesAsText("originalFilename")).containsExactly("3.wav", "2.wav");
        assertThat(pageOne.get("items").get(0).get("id").asText()).isEqualTo(third);
        assertThat(pageOne.get("items").get(1).get("id").asText()).isEqualTo(second);
        assertThat(pageTwo.get("items")).hasSize(1);
        assertThat(pageTwo.get("items").get(0).get("id").asText()).isEqualTo(first);
        // Oversized and negative paging values are clamped instead of failing.
        assertThat(get(user, "/api/v1/calls?page=-5&size=100000").getBody().get("size").asInt()).isEqualTo(100);
    }

    // ----------------------------------------------------------------- profile

    @Test
    void profileCanBeUpdatedPartially() {
        Session user = register("profile");

        ResponseEntity<JsonNode> renamed = patchMe(user, Map.of("fullName", "  Lê Thị Hoa  "));
        ResponseEntity<JsonNode> phoneSet = patchMe(user, Map.of("phoneNumber", "090.123.4567"));
        ResponseEntity<JsonNode> alertOff = patchMe(user, Map.of("blacklistAlertEnabled", false));

        assertThat(renamed.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(renamed.getBody().get("fullName").asText()).isEqualTo("Lê Thị Hoa");
        assertThat(phoneSet.getBody().get("phoneNumber").asText()).isEqualTo("+84901234567");
        assertThat(alertOff.getBody().get("blacklistAlertEnabled").asBoolean()).isFalse();

        JsonNode me = get(user, "/api/v1/users/me").getBody();
        assertThat(me.get("fullName").asText()).isEqualTo("Lê Thị Hoa");
        assertThat(me.get("phoneNumber").asText()).isEqualTo("+84901234567");
        assertThat(me.get("blacklistAlertEnabled").asBoolean()).isFalse();

        assertThat(patchMe(user, Map.of("blacklistAlertEnabled", true)).getBody().get("blacklistAlertEnabled")
                .asBoolean()).isTrue();
        assertThat(patchMe(user, Map.of("phoneNumber", "")).getBody().get("phoneNumber").isNull()).isTrue();
        // Fields that were not sent kept their values.
        assertThat(get(user, "/api/v1/users/me").getBody().get("fullName").asText()).isEqualTo("Lê Thị Hoa");
    }

    @Test
    void profileUpdateValidatesInputAndIgnoresProtectedFields() {
        Session user = register("profile-invalid");

        assertError(patchMe(user, Map.of("fullName", "   ")), HttpStatus.BAD_REQUEST, "VALIDATION_FAILED");
        assertError(patchMe(user, Map.of("fullName", "x".repeat(101))), HttpStatus.BAD_REQUEST, "VALIDATION_FAILED");
        assertError(patchMe(user, Map.of("phoneNumber", "call me")), HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER");

        ResponseEntity<JsonNode> sneaky = patchMe(user, Map.of("email", "attacker@example.com", "status", "LOCKED",
                "roles", List.of("ADMIN"), "id", UUID.randomUUID().toString()));

        assertThat(sneaky.getStatusCode()).isEqualTo(HttpStatus.OK);
        JsonNode me = get(user, "/api/v1/users/me").getBody();
        assertThat(me.get("email").asText()).isEqualTo(user.email);
        assertThat(me.get("status").asText()).isEqualTo("ACTIVE");
        assertThat(me.get("roles")).hasSize(1);
        assertThat(me.get("roles").get(0).asText()).isEqualTo("USER");
        assertThat(me.get("id").asText()).isEqualTo(user.id.toString());
    }

    @Test
    void profileUpdateRequiresAuthentication() {
        assertThat(patchMe(Session.ANONYMOUS, Map.of("fullName", "Nobody")).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    // ----------------------------------------------------------------- helpers

    /** A signed-in user; {@code ANONYMOUS} has no token. */
    private record Session(String accessToken, UUID id, String email) {
        static final Session ANONYMOUS = new Session(null, null, null);
    }

    private Session register(String prefix) {
        String email = prefix + "-" + UUID.randomUUID() + "@example.com";
        ResponseEntity<JsonNode> response = rest.postForEntity("/api/v1/auth/register",
                Map.of("email", email, "password", PASSWORD, "fullName", "Test User"), JsonNode.class);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        return new Session(response.getBody().get("accessToken").asText(),
                UUID.fromString(response.getBody().get("user").get("id").asText()), email);
    }

    private ResponseEntity<JsonNode> upload(Session session, String filename, byte[] content,
            Map<String, String> fields) {
        return upload(session, filename, content, fields, MediaType.parseMediaType("audio/wav"));
    }

    private ResponseEntity<JsonNode> upload(Session session, String filename, byte[] content,
            Map<String, String> fields, MediaType partType) {
        HttpHeaders partHeaders = new HttpHeaders();
        partHeaders.setContentType(partType);
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("audio", new HttpEntity<>(new ByteArrayResource(content) {
            @Override
            public String getFilename() {
                return filename;
            }
        }, partHeaders));
        fields.forEach(form::add);
        return rest.exchange("/api/v1/calls", HttpMethod.POST, new HttpEntity<>(form, multipart(session)),
                JsonNode.class);
    }

    private ResponseEntity<JsonNode> get(Session session, String path) {
        return rest.exchange(path, HttpMethod.GET, new HttpEntity<>(bearer(session)), JsonNode.class);
    }

    private ResponseEntity<JsonNode> patchMe(Session session, Map<String, Object> body) {
        HttpHeaders headers = bearer(session);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange("/api/v1/users/me", HttpMethod.PATCH, new HttpEntity<>(body, headers), JsonNode.class);
    }

    private static HttpHeaders bearer(Session session) {
        HttpHeaders headers = new HttpHeaders();
        if (session.accessToken != null) {
            headers.setBearerAuth(session.accessToken);
        }
        return headers;
    }

    private static HttpHeaders multipart(Session session) {
        HttpHeaders headers = bearer(session);
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        return headers;
    }

    private static void assertError(ResponseEntity<JsonNode> response, HttpStatus status, String code) {
        assertThat(response.getStatusCode()).isEqualTo(status);
        assertThat(response.getBody().get("code").asText()).isEqualTo(code);
    }

    private List<String> objectsOf(Session session) {
        return s3.listObjectsV2(b -> b.bucket(storage.bucket()).prefix("calls/" + session.id + "/")).contents()
                .stream().map(S3Object::key).toList();
    }

    private static String sha256(byte[] content) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
    }

    /** A valid WAV file: 16 kHz, mono, 16-bit PCM, a 440 Hz tone of the given length. */
    private static byte[] wav(int seconds) {
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
