package com.ivpds;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;

/**
 * Real MinIO server, using the image that docker-compose builds from source. MinIO publishes no
 * official image any more, so run {@code docker compose build minio} once before the tests.
 */
public class MinioContainer extends GenericContainer<MinioContainer> {

    public static final String ACCESS_KEY = "test-access-key";
    public static final String SECRET_KEY = "test-secret-key";

    private static final int API_PORT = 9000;

    public MinioContainer() {
        super("ivpds/minio:RELEASE.2025-10-15T17-29-55Z");
        withEnv("MINIO_ROOT_USER", ACCESS_KEY);
        withEnv("MINIO_ROOT_PASSWORD", SECRET_KEY);
        withExposedPorts(API_PORT);
        waitingFor(Wait.forHttp("/minio/health/live").forPort(API_PORT));
    }

    public String endpoint() {
        return "http://" + getHost() + ":" + getMappedPort(API_PORT);
    }
}
