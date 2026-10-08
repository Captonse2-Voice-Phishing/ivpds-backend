package com.ivpds;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({TestcontainersConfig.class, MinioConfig.class})
class IvpdsApplicationTests {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void healthEndpointReportsUp() {
        ResponseEntity<JsonNode> response = rest.getForEntity("/actuator/health", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().get("status").asText()).isEqualTo("UP");
    }

    @Test
    void otherActuatorEndpointsAreNotReachableAnonymously() {
        assertThat(rest.getForEntity("/actuator/env", JsonNode.class).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(rest.getForEntity("/actuator/beans", JsonNode.class).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void openApiDocumentIsServed() {
        ResponseEntity<JsonNode> response = rest.getForEntity("/v3/api-docs", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().get("info").get("title").asText()).isEqualTo("IVPDS Backend API");
    }

    @Test
    void swaggerUiIsServed() {
        ResponseEntity<String> response = rest.getForEntity("/swagger-ui/index.html", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("swagger-ui");
    }

    @Test
    void anonymousRequestToAnyOtherRouteReturnsJsonUnauthorized() {
        ResponseEntity<JsonNode> response = rest.getForEntity("/no-such-route", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(response.getBody().get("code").asText()).isEqualTo("UNAUTHORIZED");
        assertThat(response.getBody().get("requestId").asText())
                .isEqualTo(response.getHeaders().getFirst("X-Request-Id"));
    }
}
