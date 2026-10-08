package com.ivpds;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistrar;

/** Starts MinIO and points the storage client at it. */
@TestConfiguration(proxyBeanMethods = false)
public class MinioConfig {

    @Bean
    MinioContainer minio() {
        return new MinioContainer();
    }

    @Bean
    DynamicPropertyRegistrar storageProperties(MinioContainer minio) {
        return registry -> {
            registry.add("ivpds.storage.endpoint", minio::endpoint);
            registry.add("ivpds.storage.access-key", () -> MinioContainer.ACCESS_KEY);
            registry.add("ivpds.storage.secret-key", () -> MinioContainer.SECRET_KEY);
        };
    }
}
