package com.ivpds.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/** Tài khoản người dùng (bảng {@code users}). */
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    /** Email đăng nhập, luôn lưu ở dạng chữ thường. */
    @Column(nullable = false)
    private String email;

    /** Mật khẩu đã băm bằng BCrypt, không bao giờ lưu mật khẩu gốc. */
    @Column(name = "password_hash", nullable = false, length = 100)
    private String passwordHash;

    @Column(name = "full_name", nullable = false, length = 100)
    private String fullName;

    @Column(name = "phone_number", length = 20)
    private String phoneNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private UserStatus status = UserStatus.ACTIVE;

    /** Người dùng có muốn nhận cảnh báo khi số gọi đến nằm trong blacklist hay không. */
    @Column(name = "blacklist_alert_enabled", nullable = false)
    private boolean blacklistAlertEnabled = true;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    /** Các vai trò của người dùng (bảng nối {@code user_roles}); nạp ngay vì luôn cần khi cấp token. */
    @ManyToMany(fetch = FetchType.EAGER)
    @JoinTable(name = "user_roles",
            joinColumns = @JoinColumn(name = "user_id"),
            inverseJoinColumns = @JoinColumn(name = "role_id"))
    private Set<Role> roles = new HashSet<>();

    /** Constructor rỗng dành cho JPA. */
    protected User() {
    }

    /** Tạo tài khoản mới; email và số điện thoại phải được chuẩn hóa trước khi truyền vào. */
    public User(String email, String passwordHash, String fullName, String phoneNumber) {
        this.email = email;
        this.passwordHash = passwordHash;
        this.fullName = fullName;
        this.phoneNumber = phoneNumber;
    }

    /** Ghi thời điểm tạo ngay trước khi lưu lần đầu. */
    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
        updatedAt = createdAt;
    }

    /** Cập nhật thời điểm sửa đổi mỗi khi bản ghi thay đổi. */
    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

    /** Gán thêm một vai trò cho người dùng. */
    public void addRole(Role role) {
        roles.add(role);
    }

    /** Thay mật khẩu (truyền vào giá trị đã băm). */
    public void changePasswordHash(String passwordHash) {
        this.passwordHash = passwordHash;
    }

    /** Đổi họ tên. */
    public void rename(String fullName) {
        this.fullName = fullName;
    }

    /** Đổi số điện thoại; {@code null} nghĩa là xóa số đã lưu. */
    public void changePhoneNumber(String phoneNumber) {
        this.phoneNumber = phoneNumber;
    }

    /** Bật hoặc tắt cảnh báo blacklist. */
    public void setBlacklistAlertEnabled(boolean enabled) {
        this.blacklistAlertEnabled = enabled;
    }

    /** Tài khoản có đang hoạt động (không bị khóa) hay không. */
    public boolean isActive() {
        return status == UserStatus.ACTIVE;
    }

    /** Danh sách tên vai trò, sắp xếp theo bảng chữ cái. */
    public List<String> roleNames() {
        return roles.stream().map(Role::getName).sorted().toList();
    }

    public UUID getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getFullName() {
        return fullName;
    }

    public String getPhoneNumber() {
        return phoneNumber;
    }

    public UserStatus getStatus() {
        return status;
    }

    public boolean isBlacklistAlertEnabled() {
        return blacklistAlertEnabled;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
