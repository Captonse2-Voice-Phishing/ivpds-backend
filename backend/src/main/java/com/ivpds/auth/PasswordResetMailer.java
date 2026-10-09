package com.ivpds.auth;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

/** Gửi email chứa mã đặt lại mật khẩu qua SMTP. */
@Component
class PasswordResetMailer {

    private static final Logger log = LoggerFactory.getLogger(PasswordResetMailer.class);

    private final JavaMailSender mailSender;
    private final String from;

    PasswordResetMailer(JavaMailSender mailSender, @Value("${ivpds.mail.from}") String from) {
        this.mailSender = mailSender;
        this.from = from;
    }

    /**
     * Gửi mã đặt lại mật khẩu tới địa chỉ {@code to}.
     *
     * @param validFor thời hạn hiệu lực của mã, để ghi trong nội dung thư
     * @return {@code false} nếu không gửi được thư tới máy chủ SMTP (lỗi được ghi log, không ném ra)
     */
    boolean send(String to, String code, Duration validFor) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject("IVPDS - Mã đặt lại mật khẩu");
        message.setText("""
                Xin chào,

                Mã đặt lại mật khẩu IVPDS của bạn là: %s

                Mã có hiệu lực trong %d phút. Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.
                Không chia sẻ mã này cho bất kỳ ai.
                """.formatted(code, validFor.toMinutes()));
        try {
            mailSender.send(message);
            return true;
        } catch (MailException e) {
            log.error("Could not send password reset email", e);
            return false;
        }
    }
}
