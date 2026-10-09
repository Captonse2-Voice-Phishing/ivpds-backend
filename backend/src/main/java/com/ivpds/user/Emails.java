package com.ivpds.user;

import java.util.Locale;

/** Tiện ích xử lý địa chỉ email. */
public final class Emails {

    private Emails() {
    }

    /** Chuẩn hóa email để lưu và tra cứu: bỏ khoảng trắng hai đầu và chuyển thành chữ thường. */
    public static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
