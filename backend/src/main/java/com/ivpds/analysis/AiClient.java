package com.ivpds.analysis;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.ivpds.phishingpattern.ActivePhishingPatterns.Pattern;
import java.io.InputStream;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.http.HttpClient;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.converter.HttpMessageConversionException;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/**
 * Client gọi AI service (FastAPI). Đây là nơi duy nhất trong backend nói chuyện với AI service.
 *
 * <p>Mọi lỗi (không kết nối được, quá thời gian, HTTP lỗi, nội dung trả về sai) đều được chuyển thành
 * {@link AiServiceException} kèm mã lỗi. Lớp này không bao giờ tự tạo ra transcript hay điểm rủi ro.
 */
@Component
public class AiClient {

    static final String API_KEY_HEADER = "X-API-Key";
    static final String REQUEST_ID_HEADER = "X-Request-Id";

    private static final Set<String> RISK_LEVELS = Set.of("LOW", "MEDIUM", "HIGH");

    private final RestClient transcriptionClient;
    private final RestClient riskClient;

    public AiClient(RestClient.Builder builder, AiProperties properties) {
        // Hai client khác nhau ở thời gian chờ: nhận dạng giọng nói chậm hơn đánh giá rủi ro rất nhiều.
        this.transcriptionClient = build(builder, properties, properties.transcriptionTimeout());
        this.riskClient = build(builder, properties, properties.riskTimeout());
    }

    private static RestClient build(RestClient.Builder builder, AiProperties properties, Duration readTimeout) {
        // HTTP/1.1: server của AI service (uvicorn) không dùng HTTP/2.
        HttpClient http = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(properties.connectTimeout())
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(readTimeout);
        return builder.clone()
                .baseUrl(properties.baseUrl().toString())
                .defaultHeader(API_KEY_HEADER, properties.apiKey())
                .requestFactory(factory)
                .build();
    }

    /**
     * Gửi audio của cuộc gọi sang AI service để chuyển thành văn bản.
     *
     * @param content   nội dung audio; phương thức này không đóng luồng
     * @param sizeBytes số byte chính xác của audio
     * @param filename  tên file gửi kèm (AI service chỉ dùng để ghi log)
     * @param requestId mã theo dõi, gửi trong header để nối log của hai service
     * @throws AiServiceException nếu gọi thất bại hoặc kết quả không hợp lệ
     */
    public Transcription transcribe(InputStream content, long sizeBytes, String filename, String contentType,
            String requestId) {
        HttpHeaders partHeaders = new HttpHeaders();
        partHeaders.setContentType(MediaType.parseMediaType(contentType));
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("audio", new HttpEntity<>(new SizedResource(content, sizeBytes, filename), partHeaders));

        Transcription result = call(() -> transcriptionClient.post()
                .uri("/v1/transcriptions")
                .header(REQUEST_ID_HEADER, requestId)
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(body)
                .retrieve()
                .body(Transcription.class));
        if (result == null || result.transcript() == null) {
            throw invalid("The transcription response has no transcript.");
        }
        return result;
    }

    /**
     * Gửi transcript sang AI service để Risk Engine đánh giá rủi ro.
     *
     * @param customPatterns các mẫu lừa đảo đang bật do quản trị viên quản lý, để Rule Engine dùng thêm
     *
     * @throws AiServiceException nếu gọi thất bại hoặc kết quả thiếu hay sai giá trị
     */
    public RiskAssessment assessRisk(String transcript, String requestId, List<Pattern> customPatterns) {
        // Chỉ thêm trường customPatterns khi có mẫu, để yêu cầu thông thường giữ nguyên hình dạng.
        Map<String, Object> request = customPatterns.isEmpty()
                ? Map.of("text", transcript)
                : Map.of("text", transcript, "customPatterns", customPatterns);
        RiskAssessment result = call(() -> riskClient.post()
                .uri("/v1/risk-assessments")
                .header(REQUEST_ID_HEADER, requestId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(RiskAssessment.class));
        validate(result);
        return result;
    }

    /** Kiểm tra kết quả đánh giá rủi ro trước khi tin dùng: đủ trường và giá trị nằm trong khoảng cho phép. */
    static void validate(RiskAssessment result) {
        if (result == null || result.riskScore() == null || result.riskLevel() == null
                || result.confidence() == null || result.indicators() == null) {
            throw invalid("The risk assessment response is missing required fields.");
        }
        if (result.riskScore() < 0 || result.riskScore() > 100) {
            throw invalid("riskScore is outside 0-100.");
        }
        if (!RISK_LEVELS.contains(result.riskLevel())) {
            throw invalid("riskLevel is not LOW, MEDIUM or HIGH.");
        }
        if (result.confidence().isNaN() || result.confidence() < 0 || result.confidence() > 1) {
            throw invalid("confidence is outside 0-1.");
        }
        if (result.indicators().stream().anyMatch(code -> code == null || code.isBlank() || code.length() > 50)) {
            throw invalid("indicators contains an invalid code.");
        }
        Double probability = result.components() == null ? null : result.components().modelProbability();
        if (probability != null && (probability.isNaN() || probability < 0 || probability > 1)) {
            throw invalid("modelProbability is outside 0-1.");
        }
    }

    private static AiServiceException invalid(String message) {
        return new AiServiceException(AiServiceException.INVALID_RESPONSE, message, null);
    }

    /** Thực hiện một lần gọi và chuyển mọi lỗi của tầng HTTP thành {@link AiServiceException}. */
    private static <T> T call(java.util.function.Supplier<T> request) {
        try {
            return request.get();
        } catch (RestClientResponseException e) {
            throw fromHttpError(e);
        } catch (ResourceAccessException e) {
            throw fromIoError(e);
        } catch (RestClientException | HttpMessageConversionException e) {
            // Kết nối được và có mã 2xx nhưng nội dung không đọc được (không phải JSON, sai kiểu dữ liệu).
            throw new AiServiceException(AiServiceException.INVALID_RESPONSE,
                    "The AI service response could not be read.", e);
        }
    }

    /** Lỗi trước khi nhận được phản hồi HTTP: phân biệt quá thời gian với không kết nối được. */
    private static AiServiceException fromIoError(ResourceAccessException e) {
        for (Throwable cause = e; cause != null; cause = cause.getCause()) {
            if (cause instanceof HttpTimeoutException || cause instanceof SocketTimeoutException) {
                return new AiServiceException(AiServiceException.TIMEOUT, "The AI service did not answer in time.", e);
            }
            if (cause instanceof ConnectException) {
                break;
            }
        }
        return new AiServiceException(AiServiceException.UNAVAILABLE, "The AI service could not be reached.", e);
    }

    /** AI service trả mã lỗi HTTP: giữ mã lỗi của nó khi có, vì đó là nguyên nhân chính xác nhất. */
    private static AiServiceException fromHttpError(RestClientResponseException e) {
        int status = e.getStatusCode().value();
        String aiCode = errorCode(e);
        String message = "AI service answered %d%s.".formatted(status, aiCode == null ? "" : " " + aiCode);
        if (status == 401 || status == 403) {
            return new AiServiceException(AiServiceException.AUTH_FAILED, message, e);
        }
        if (aiCode != null && (status == 413 || status == 422 || status == 503)) {
            return new AiServiceException(aiCode, message, e);
        }
        if (status >= 500) {
            return new AiServiceException(status == 503 ? AiServiceException.UNAVAILABLE : AiServiceException.ERROR,
                    message, e);
        }
        return new AiServiceException(AiServiceException.REQUEST_REJECTED, message, e);
    }

    /** Đọc trường {@code code} trong body lỗi của AI service; trả null nếu body không đúng cấu trúc. */
    private static String errorCode(RestClientResponseException e) {
        try {
            ErrorBody body = e.getResponseBodyAs(ErrorBody.class);
            String code = body == null ? null : body.code();
            return code != null && code.matches("[A-Z][A-Z0-9_]{1,49}") ? code : null;
        } catch (RuntimeException ignored) {
            return null;
        }
    }

    /** Nội dung audio kèm kích thước và tên file, để phần multipart có đủ thông tin mà không phải đọc trước vào bộ nhớ. */
    private static final class SizedResource extends InputStreamResource {

        private final long size;
        private final String filename;

        SizedResource(InputStream content, long size, String filename) {
            super(content);
            this.size = size;
            this.filename = filename;
        }

        @Override
        public long contentLength() {
            return size;
        }

        @Override
        public String getFilename() {
            return filename;
        }
    }

    /** Body lỗi của AI service; chỉ cần mã lỗi. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record ErrorBody(String code) {
    }

    /** Kết quả nhận dạng giọng nói của AI service (các trường backend dùng). */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Transcription(String transcript, String language, String sttModel, Audio audio) {

        /** Thông tin kỹ thuật của audio do FFmpeg đo được. */
        @JsonIgnoreProperties(ignoreUnknown = true)
        public record Audio(Double durationSeconds) {
        }
    }

    /** Kết quả của Risk Engine (các trường backend dùng). */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record RiskAssessment(Integer riskScore, String riskLevel, Double confidence, List<String> indicators,
            Components components, String modelVersion, String rulesetVersion, String riskEngineVersion) {

        /** Các thành phần của điểm rủi ro; backend lưu xác suất của model để truy vết. */
        @JsonIgnoreProperties(ignoreUnknown = true)
        public record Components(Double modelProbability) {
        }
    }
}
