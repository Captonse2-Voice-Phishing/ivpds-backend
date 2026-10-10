package com.ivpds.phishingpattern;

import com.ivpds.common.PageResponse;
import com.ivpds.common.error.ApiException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.Locale;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * API quản lý mẫu lừa đảo, chỉ dành cho ADMIN. Nghiệp vụ ở đây chỉ là thêm, sửa, xóa, tìm kiếm nên nằm ngay trong
 * controller thay vì tách thành một lớp service riêng. Mẫu đang bật được Rule Engine dùng từ lần phân tích kế
 * tiếp; mỗi mẫu là một cụm từ ít nhất hai từ, gắn với một mã dấu hiệu Rule Engine biết.
 */
@RestController
@RequestMapping("/api/v1/admin/phishing-patterns")
@Tag(name = "Phishing patterns")
public class PhishingPatternController {

    private static final int MAX_PAGE_SIZE = 100;
    private static final String CODE_FORMAT = "[A-Z][A-Z0-9_]{1,49}";

    private final PhishingPatternRepository patterns;

    public PhishingPatternController(PhishingPatternRepository patterns) {
        this.patterns = patterns;
    }

    /** Thêm một mẫu. Mã dấu hiệu viết hoa, dạng OTP_REQUEST. */
    @Schema(name = "PhishingPatternCreateRequest")
    public record CreateRequest(
            @NotBlank @Size(max = 150) String name,
            @NotBlank @Pattern(regexp = CODE_FORMAT, message = "must look like OTP_REQUEST") String indicatorCode,
            @NotBlank @Size(max = ActivePhishingPatterns.MAX_PHRASE_LENGTH) String pattern,
            @Size(max = 2000) String description) {
    }

    /** Sửa một mẫu; trường nào không gửi thì giữ nguyên. */
    @Schema(name = "PhishingPatternUpdateRequest")
    public record UpdateRequest(
            @Size(min = 1, max = 150) @Pattern(regexp = ".*\\S.*", message = "must not be blank") String name,
            @Pattern(regexp = CODE_FORMAT, message = "must look like OTP_REQUEST") String indicatorCode,
            @Size(min = 1, max = ActivePhishingPatterns.MAX_PHRASE_LENGTH)
            @Pattern(regexp = "(?s).*\\S.*", message = "must not be blank") String pattern,
            @Size(max = 2000) String description,
            Boolean active) {
    }

    /** Một mẫu lừa đảo trả về cho quản trị viên. */
    public record PatternResponse(UUID id, String name, String indicatorCode, String pattern, String description,
            boolean active, UUID createdBy, Instant createdAt, Instant updatedAt) {

        static PatternResponse from(PhishingPattern p) {
            return new PatternResponse(p.getId(), p.getName(), p.getIndicatorCode(), p.getPattern(),
                    p.getDescription(), p.isActive(), p.getCreatedBy(), p.getCreatedAt(), p.getUpdatedAt());
        }
    }

    @GetMapping
    @Transactional(readOnly = true)
    @Operation(summary = "Admin: list phishing patterns, newest first")
    public PageResponse<PatternResponse> list(@RequestParam(required = false) String query,
            @RequestParam(required = false) String indicatorCode,
            @RequestParam(required = false) Boolean active,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        String text = query == null ? "" : query.trim().toLowerCase(Locale.ROOT);
        String code = indicatorCode == null ? "" : indicatorCode.trim();
        return PageResponse.of(patterns.search(text, code, active,
                PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE))), PatternResponse::from);
    }

    @GetMapping("/{id}")
    @Transactional(readOnly = true)
    public PatternResponse get(@PathVariable UUID id) {
        return PatternResponse.from(find(id));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    @Operation(summary = "Admin: add a phishing pattern")
    public PatternResponse create(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody CreateRequest request) {
        requireUsable(request.indicatorCode(), request.pattern());
        String description = request.description() == null || request.description().isBlank()
                ? null : request.description().trim();
        return PatternResponse.from(patterns.save(new PhishingPattern(request.name().trim(), request.indicatorCode(),
                request.pattern().trim(), description, UUID.fromString(jwt.getSubject()))));
    }

    @PatchMapping("/{id}")
    @Transactional
    @Operation(summary = "Admin: change a phishing pattern or switch it on or off")
    public PatternResponse update(@PathVariable UUID id, @Valid @RequestBody UpdateRequest request) {
        PhishingPattern pattern = find(id);
        requireUsable(request.indicatorCode() == null ? pattern.getIndicatorCode() : request.indicatorCode(),
                request.pattern() == null ? pattern.getPattern() : request.pattern());
        pattern.update(request.name() == null ? null : request.name().trim(), request.indicatorCode(),
                request.pattern() == null ? null : request.pattern().trim(), request.description(), request.active());
        return PatternResponse.from(pattern);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Transactional
    public void delete(@PathVariable UUID id) {
        patterns.delete(find(id));
    }

    /**
     * Từ chối mẫu mà Rule Engine không dùng được: mã dấu hiệu lạ, hoặc cụm từ chỉ có một từ (một từ đơn lẻ
     * khớp quá nhiều câu bình thường).
     */
    private static void requireUsable(String indicatorCode, String phrase) {
        if (!ActivePhishingPatterns.INDICATOR_CODES.contains(indicatorCode)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "UNKNOWN_INDICATOR_CODE",
                    "indicatorCode must be one of " + new java.util.TreeSet<>(ActivePhishingPatterns.INDICATOR_CODES) + ".");
        }
        if (!ActivePhishingPatterns.usable(indicatorCode, phrase)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "PATTERN_TOO_SHORT",
                    "pattern must be a phrase of at least two words.");
        }
    }

    private PhishingPattern find(UUID id) {
        return patterns.findById(id).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND,
                "PHISHING_PATTERN_NOT_FOUND", "Phishing pattern not found."));
    }
}
