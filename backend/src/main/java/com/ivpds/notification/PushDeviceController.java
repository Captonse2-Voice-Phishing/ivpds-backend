package com.ivpds.notification;

import com.ivpds.common.error.ApiException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * API đăng ký thiết bị nhận thông báo đẩy của người dùng đang đăng nhập. Ứng dụng gọi đăng ký sau mỗi lần đăng
 * nhập (và khi token đổi), gọi gỡ khi đăng xuất. Nghiệp vụ chỉ là thêm, xem, xóa nên nằm ngay trong controller.
 */
@RestController
@RequestMapping("/api/v1/notifications/devices")
@Tag(name = "Notifications")
public class PushDeviceController {

    /** Số thiết bị tối đa của một người dùng; đăng ký thêm thì thiết bị lâu không dùng nhất bị gỡ. */
    static final int MAX_DEVICES_PER_USER = 10;
    private static final String EXPO_TOKEN = "Expo(nent)?PushToken\\[[A-Za-z0-9_-]{1,200}\\]";

    private final PushDeviceRepository devices;

    public PushDeviceController(PushDeviceRepository devices) {
        this.devices = devices;
    }

    /** Đăng ký một thiết bị bằng Expo push token của nó. */
    @Schema(name = "DeviceRegisterRequest")
    public record RegisterRequest(
            @NotBlank @Size(max = 255)
            @Pattern(regexp = EXPO_TOKEN, message = "must be an Expo push token such as ExponentPushToken[...]")
            String token,
            @NotNull PushDevice.Platform platform) {
    }

    /** Một thiết bị đã đăng ký. */
    public record DeviceResponse(UUID id, String token, PushDevice.Platform platform, Instant createdAt,
            Instant lastSeenAt) {

        static DeviceResponse from(PushDevice d) {
            return new DeviceResponse(d.getId(), d.getToken(), d.getPlatform(), d.getCreatedAt(), d.getLastSeenAt());
        }
    }

    @PutMapping
    @Transactional
    @Operation(summary = "Register this device for push notifications (call again whenever the token changes)")
    public DeviceResponse register(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody RegisterRequest request) {
        UUID userId = userId(jwt);
        devices.register(userId, request.token(), request.platform().name());
        List<PushDevice> mine = devices.findByUserIdOrderByLastSeenAtDesc(userId);
        if (mine.size() > MAX_DEVICES_PER_USER) {
            devices.deleteAllInBatch(mine.subList(MAX_DEVICES_PER_USER, mine.size()));
        }
        return mine.stream().filter(device -> device.getToken().equals(request.token())).findFirst()
                .map(DeviceResponse::from)
                .orElseThrow(() -> new ApiException(HttpStatus.CONFLICT, "DEVICE_REGISTRATION_CONFLICT",
                        "The device was registered by another account at the same time. Try again."));
    }

    @GetMapping
    @Transactional(readOnly = true)
    @Operation(summary = "List the signed-in user's registered devices")
    public List<DeviceResponse> list(@AuthenticationPrincipal Jwt jwt) {
        return devices.findByUserIdOrderByLastSeenAtDesc(userId(jwt)).stream().map(DeviceResponse::from).toList();
    }

    /** Gỡ một thiết bị (khi đăng xuất). Token không có hoặc không phải của mình thì không làm gì. */
    @DeleteMapping
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Transactional
    @Operation(summary = "Stop sending push notifications to a device (call on sign-out)")
    public void unregister(@AuthenticationPrincipal Jwt jwt, @RequestParam String token) {
        devices.deleteByUserIdAndToken(userId(jwt), token);
    }

    private static UUID userId(Jwt jwt) {
        return UUID.fromString(jwt.getSubject());
    }
}
