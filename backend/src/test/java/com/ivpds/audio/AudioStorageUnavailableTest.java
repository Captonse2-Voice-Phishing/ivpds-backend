package com.ivpds.audio;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ivpds.common.error.ApiException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.InputStreamSource;
import org.springframework.http.HttpStatus;

/**
 * Uses the real S3 client against endpoints that are down, to check what callers see when the
 * object store is unavailable. Both cases were found by stopping MinIO under the running stack:
 * uploads first failed with a generic 500 (a retried attempt could not re-read the stream), then
 * hung for over 100 seconds before succeeding long after the client had given up.
 */
class AudioStorageUnavailableTest {

    private static final byte[] CONTENT = "RIFF....WAVE".getBytes();

    @Test
    void uploadFailsWithStorageUnavailableAndRereadsTheContentOnEachAttempt() {
        AudioStorage storage = storageAt("http://127.0.0.1:1", Duration.ofSeconds(30));
        AtomicInteger timesOpened = new AtomicInteger();
        InputStreamSource source = () -> {
            timesOpened.incrementAndGet();
            return new ByteArrayResource(CONTENT).getInputStream();
        };

        assertStorageUnavailable(() -> storage.put("calls/a/b.wav", source, CONTENT.length, "audio/wav"));
        // The client retried, and every attempt got a fresh stream.
        assertThat(timesOpened.get()).isGreaterThan(1);
    }

    @Test
    void downloadFailsWithStorageUnavailable() {
        AudioStorage storage = storageAt("http://127.0.0.1:1", Duration.ofSeconds(30));

        assertStorageUnavailable(() -> storage.open("calls/a/b.wav"));
    }

    @Test
    void operationsGiveUpAfterTheRequestTimeoutWhenTheStoreAcceptsConnectionsButNeverAnswers() throws Exception {
        // The OS completes the TCP handshake for a listening socket, but nothing ever replies.
        try (ServerSocket silent = new ServerSocket(0, 50, InetAddress.getLoopbackAddress())) {
            AudioStorage storage = storageAt("http://127.0.0.1:" + silent.getLocalPort(), Duration.ofSeconds(2));
            Instant start = Instant.now();

            assertStorageUnavailable(() -> storage.put("calls/a/b.wav", new ByteArrayResource(CONTENT),
                    CONTENT.length, "audio/wav"));

            assertThat(Duration.between(start, Instant.now())).isBetween(Duration.ofSeconds(2), Duration.ofSeconds(10));
        }
    }

    private static AudioStorage storageAt(String endpoint, Duration requestTimeout) {
        StorageProperties properties = new StorageProperties(URI.create(endpoint), "us-east-1", "key", "secret",
                "ivpds-audio", true, Duration.ofSeconds(1), requestTimeout);
        return new AudioStorage(new StorageConfig().s3Client(properties), properties);
    }

    private static void assertStorageUnavailable(Runnable operation) {
        assertThatThrownBy(operation::run)
                .isInstanceOf(ApiException.class)
                .satisfies(e -> {
                    assertThat(((ApiException) e).getStatus()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
                    assertThat(((ApiException) e).getCode()).isEqualTo("STORAGE_UNAVAILABLE");
                });
    }
}
