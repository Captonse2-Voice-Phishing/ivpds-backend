package com.ivpds.auth;

import com.ivpds.user.Emails;
import com.ivpds.user.Role;
import com.ivpds.user.RoleRepository;
import com.ivpds.user.User;
import com.ivpds.user.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * Tạo tài khoản ADMIN đầu tiên từ cấu hình khi ứng dụng khởi động, vì admin không thể tự đăng ký.
 * Không làm gì nếu chưa cấu hình email admin hoặc tài khoản đã tồn tại; mật khẩu của tài khoản
 * đã tồn tại không bao giờ bị thay đổi.
 */
@Component
public class AdminBootstrap implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AdminBootstrap.class);
    private static final int MIN_PASSWORD_LENGTH = 8;

    private final AdminBootstrapProperties properties;
    private final UserRepository users;
    private final RoleRepository roles;
    private final PasswordEncoder passwordEncoder;

    public AdminBootstrap(AdminBootstrapProperties properties, UserRepository users, RoleRepository roles,
            PasswordEncoder passwordEncoder) {
        this.properties = properties;
        this.users = users;
        this.roles = roles;
        this.passwordEncoder = passwordEncoder;
    }

    /** Chạy một lần sau khi ứng dụng khởi động xong. Mật khẩu quá ngắn thì dừng khởi động. */
    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (!StringUtils.hasText(properties.email())) {
            return;
        }
        String email = Emails.normalize(properties.email());
        if (users.findByNormalizedEmail(email).isPresent()) {
            return;
        }
        if (properties.password() == null || properties.password().length() < MIN_PASSWORD_LENGTH) {
            throw new IllegalStateException(
                    "ADMIN_PASSWORD must be at least " + MIN_PASSWORD_LENGTH + " characters to create the admin account");
        }
        User admin = new User(email, passwordEncoder.encode(properties.password()), properties.fullName(), null);
        admin.addRole(roles.findByName(Role.ADMIN)
                .orElseThrow(() -> new IllegalStateException("Role ADMIN is missing from the database")));
        users.save(admin);
        log.info("Created bootstrap admin account {}", email);
    }
}
