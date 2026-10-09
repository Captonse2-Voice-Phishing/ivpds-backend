package com.ivpds.common;

import java.util.regex.Pattern;

/**
 * Chuẩn hóa số điện thoại về một dạng duy nhất, để cùng một số luôn so sánh bằng nhau
 * (hồ sơ người dùng, số người gọi, tra cứu blacklist).
 *
 * <ul>
 *   <li>Bỏ khoảng trắng, dấu chấm, dấu gạch ngang và dấu ngoặc.</li>
 *   <li>Số nội địa Việt Nam ({@code 0901234567}) và dạng {@code 84...} được đổi thành {@code +84...}.</li>
 *   <li>Số đã bắt đầu bằng {@code +} được giữ nguyên.</li>
 *   <li>Các số khác (ví dụ tổng đài {@code 19001234}) được giữ ở dạng chỉ gồm chữ số.</li>
 * </ul>
 */
public final class PhoneNumbers {

    private static final Pattern SEPARATORS = Pattern.compile("[\\s.()-]");
    private static final Pattern CANONICAL = Pattern.compile("\\+?[0-9]{6,15}");
    private static final String VIETNAM = "+84";

    private PhoneNumbers() {
    }

    /**
     * Chuẩn hóa một số điện thoại.
     *
     * @return số đã chuẩn hóa, hoặc {@code null} nếu đầu vào rỗng
     * @throws IllegalArgumentException nếu đầu vào không phải số điện thoại
     */
    public static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String digits = SEPARATORS.matcher(raw.trim()).replaceAll("");
        if (!CANONICAL.matcher(digits).matches()) {
            throw new IllegalArgumentException("Not a phone number: must contain 6 to 15 digits");
        }
        if (digits.startsWith("+")) {
            return digits;
        }
        if (digits.startsWith("0") && digits.length() >= 10) {
            return VIETNAM + digits.substring(1);
        }
        if (digits.startsWith("84") && digits.length() >= 11) {
            return "+" + digits;
        }
        return digits;
    }
}
