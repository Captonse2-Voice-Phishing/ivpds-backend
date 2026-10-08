package com.ivpds.common.error;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.security.oauth2.resource.servlet.OAuth2ResourceServerAutoConfiguration;
import org.springframework.boot.autoconfigure.security.servlet.SecurityAutoConfiguration;
import org.springframework.boot.autoconfigure.security.servlet.SecurityFilterAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// Security is covered by AuthFlowIntegrationTest; here it is switched off to test error mapping alone.
@WebMvcTest(controllers = GlobalExceptionHandlerTest.ProbeController.class,
        excludeAutoConfiguration = {SecurityAutoConfiguration.class, SecurityFilterAutoConfiguration.class,
                OAuth2ResourceServerAutoConfiguration.class})
@Import(GlobalExceptionHandlerTest.ProbeController.class)
class GlobalExceptionHandlerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void validRequestPassesThrough() throws Exception {
        mockMvc.perform(post("/probe/validate").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"An\",\"age\":30}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("An"));
    }

    @Test
    void invalidBodyReturnsFieldErrors() throws Exception {
        mockMvc.perform(post("/probe/validate").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"age\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.path").value("/probe/validate"))
                .andExpect(jsonPath("$.timestamp").exists())
                .andExpect(jsonPath("$.requestId").isNotEmpty())
                .andExpect(jsonPath("$.fieldErrors[*].field", containsInAnyOrder("name", "age")));
    }

    @Test
    void malformedJsonReturnsMalformedRequestWithoutParserDetails() throws Exception {
        mockMvc.perform(post("/probe/validate").contentType(MediaType.APPLICATION_JSON).content("{not json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MALFORMED_REQUEST"))
                .andExpect(jsonPath("$.fieldErrors").doesNotExist())
                .andExpect(content().string(not(containsString("Jackson"))))
                .andExpect(content().string(not(containsString("JSON parse error"))));
    }

    @Test
    void apiExceptionKeepsItsStatusCodeAndMessage() throws Exception {
        mockMvc.perform(get("/probe/conflict"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.code").value("PROBE_CONFLICT"))
                .andExpect(jsonPath("$.message").value("Probe conflict."));
    }

    @Test
    void unexpectedExceptionReturns500WithoutLeakingDetails() throws Exception {
        mockMvc.perform(get("/probe/boom"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.message").value("An unexpected error occurred."))
                .andExpect(content().string(not(containsString("secret internal detail"))))
                .andExpect(content().string(not(containsString("IllegalStateException"))));
    }

    @Test
    void unknownRouteReturns404() throws Exception {
        mockMvc.perform(get("/probe/does-not-exist"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("NOT_FOUND"))
                .andExpect(jsonPath("$.path").value("/probe/does-not-exist"));
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mockMvc.perform(post("/probe/conflict"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.code").value("METHOD_NOT_ALLOWED"));
    }

    @Test
    void unsupportedMediaTypeReturns415() throws Exception {
        mockMvc.perform(post("/probe/validate").contentType(MediaType.TEXT_PLAIN).content("hello"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
    }

    @Test
    void missingParameterReturns400() throws Exception {
        mockMvc.perform(get("/probe/param"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_REQUEST"));
    }

    @Test
    void parameterOfWrongTypeReturns400() throws Exception {
        mockMvc.perform(get("/probe/param").param("n", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BAD_REQUEST"));
    }

    @Test
    void errorBodyCarriesTheSameRequestIdAsTheResponseHeader() throws Exception {
        mockMvc.perform(get("/probe/conflict").header("X-Request-Id", "req-123"))
                .andExpect(header().string("X-Request-Id", "req-123"))
                .andExpect(jsonPath("$.requestId").value("req-123"));
    }

    @RestController
    static class ProbeController {

        record Payload(@NotBlank String name, @Min(1) int age) {
        }

        @PostMapping("/probe/validate")
        Payload validate(@Valid @RequestBody Payload payload) {
            return payload;
        }

        @GetMapping("/probe/conflict")
        void conflict() {
            throw new ApiException(HttpStatus.CONFLICT, "PROBE_CONFLICT", "Probe conflict.");
        }

        @GetMapping("/probe/boom")
        void boom() {
            throw new IllegalStateException("secret internal detail");
        }

        @GetMapping("/probe/param")
        String param(@RequestParam int n) {
            return String.valueOf(n);
        }
    }
}
