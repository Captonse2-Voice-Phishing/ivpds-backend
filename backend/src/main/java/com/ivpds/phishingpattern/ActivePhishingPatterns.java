package com.ivpds.phishingpattern;

import java.text.Normalizer;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Các mẫu lừa đảo đang bật, ở dạng gửi được cho Rule Engine của AI service.
 *
 * <p>AI service không lưu mẫu: backend đọc các mẫu đang bật ở mỗi lần phân tích và gửi kèm yêu cầu, nên quản trị
 * viên thêm, sửa hay tắt một mẫu là có hiệu lực ngay ở lần phân tích kế tiếp. Rule Engine coi mỗi mẫu là một cụm
 * từ cần khớp nguyên văn, ở mức nghiêm trọng MEDIUM.
 */
@Component
public class ActivePhishingPatterns {

    private static final Logger log = LoggerFactory.getLogger(ActivePhishingPatterns.class);

    /** Các mã dấu hiệu mà Rule Engine nhận cho một mẫu (mọi mã của nó trừ COORDINATED_CALLERS). */
    public static final Set<String> INDICATOR_CODES = Set.of(
            "OTP_REQUEST", "MONEY_TRANSFER", "BANK_IMPERSONATION", "URGENCY", "ACCOUNT_LOCK_THREAT",
            "SENSITIVE_INFORMATION", "AUTHORITY_IMPERSONATION", "LEGAL_THREAT", "HARM_THREAT", "SECRECY_DEMAND",
            "REMOTE_ACCESS_REQUEST", "FINANCIAL_BAIT", "UNUSUAL_PAYMENT", "CALL_HANDOFF");
    public static final int MAX_PHRASE_LENGTH = 200;
    /** AI service nhận tối đa chừng này mẫu trong một yêu cầu. */
    private static final int MAX_PATTERNS = 500;

    private final PhishingPatternRepository patterns;

    public ActivePhishingPatterns(PhishingPatternRepository patterns) {
        this.patterns = patterns;
    }

    /**
     * Một mẫu ở dạng AI service nhận.
     *
     * @param id            id của mẫu; xuất hiện trong kết quả của Rule Engine dưới dạng {@code CUSTOM-<id>}
     * @param indicatorCode dấu hiệu mà mẫu báo
     * @param phrase        cụm từ cần khớp
     */
    public record Pattern(String id, String indicatorCode, String phrase) {
    }

    /**
     * Mọi mẫu đang bật mà Rule Engine dùng được. Mẫu không hợp lệ (tồn tại từ trước khi có quy tắc kiểm tra)
     * bị bỏ qua kèm cảnh báo trong log, để một mẫu hỏng không làm AI service từ chối cả yêu cầu.
     */
    @Transactional(readOnly = true)
    public List<Pattern> list() {
        return patterns.findByActiveTrueOrderByCreatedAtAsc().stream()
                .filter(pattern -> {
                    boolean usable = usable(pattern.getIndicatorCode(), pattern.getPattern());
                    if (!usable) {
                        log.warn("Phishing pattern {} is active but cannot be used by the rule engine", pattern.getId());
                    }
                    return usable;
                })
                .limit(MAX_PATTERNS)
                .map(pattern -> new Pattern(pattern.getId().toString(), pattern.getIndicatorCode(),
                        pattern.getPattern()))
                .toList();
    }

    /** Mẫu có dùng được không: mã dấu hiệu hợp lệ, cụm từ có ít nhất hai từ và không quá dài. */
    public static boolean usable(String indicatorCode, String phrase) {
        return indicatorCode != null && INDICATOR_CODES.contains(indicatorCode) && phrase != null
                && phrase.length() <= MAX_PHRASE_LENGTH && wordCount(phrase) >= 2;
    }

    /** Số từ của cụm từ, đếm như Rule Engine: dấu câu không tính là từ. */
    static int wordCount(String phrase) {
        // Dạng dựng sẵn (NFC) như Rule Engine, để dấu thanh viết rời không bị đếm thành ranh giới từ.
        String composed = Normalizer.normalize(phrase, Normalizer.Form.NFC);
        return (int) List.of(composed.split("[^\\p{L}\\p{N}_]+")).stream().filter(word -> !word.isEmpty()).count();
    }
}
