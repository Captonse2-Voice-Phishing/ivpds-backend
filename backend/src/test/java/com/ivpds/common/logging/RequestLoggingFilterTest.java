package com.ivpds.common.logging;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.FilterChain;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class RequestLoggingFilterTest {

    private final RequestLoggingFilter filter = new RequestLoggingFilter();

    @Test
    void generatesRequestIdWhenHeaderIsAbsent() throws Exception {
        MockHttpServletResponse response = run(null, new AtomicReference<>());

        String id = response.getHeader(RequestLoggingFilter.HEADER);
        assertThat(UUID.fromString(id)).isNotNull();
    }

    @Test
    void reusesWellFormedRequestId() throws Exception {
        MockHttpServletResponse response = run("mobile-42.a_b", new AtomicReference<>());

        assertThat(response.getHeader(RequestLoggingFilter.HEADER)).isEqualTo("mobile-42.a_b");
    }

    @Test
    void replacesRequestIdWithUnsafeCharacters() throws Exception {
        MockHttpServletResponse response = run("bad id <script>", new AtomicReference<>());

        String id = response.getHeader(RequestLoggingFilter.HEADER);
        assertThat(id).isNotEqualTo("bad id <script>");
        assertThat(UUID.fromString(id)).isNotNull();
    }

    @Test
    void replacesOverlongRequestId() throws Exception {
        String tooLong = "a".repeat(65);

        MockHttpServletResponse response = run(tooLong, new AtomicReference<>());

        assertThat(response.getHeader(RequestLoggingFilter.HEADER)).isNotEqualTo(tooLong);
    }

    @Test
    void requestIdIsInMdcDuringTheRequestAndClearedAfterwards() throws Exception {
        AtomicReference<String> seenInChain = new AtomicReference<>();

        MockHttpServletResponse response = run("req-1", seenInChain);

        assertThat(seenInChain.get()).isEqualTo("req-1");
        assertThat(response.getHeader(RequestLoggingFilter.HEADER)).isEqualTo("req-1");
        assertThat(MDC.get(RequestLoggingFilter.MDC_KEY)).isNull();
    }

    private MockHttpServletResponse run(String headerValue, AtomicReference<String> seenInChain) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/anything");
        if (headerValue != null) {
            request.addHeader(RequestLoggingFilter.HEADER, headerValue);
        }
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = (req, res) -> seenInChain.set(MDC.get(RequestLoggingFilter.MDC_KEY));
        filter.doFilter(request, response, chain);
        return response;
    }
}
