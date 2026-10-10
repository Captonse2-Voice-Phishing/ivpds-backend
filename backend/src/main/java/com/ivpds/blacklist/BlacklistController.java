package com.ivpds.blacklist;

import com.ivpds.common.PageResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * API danh sách đen. Tra cứu dành cho mọi người dùng đã đăng nhập; các API dưới {@code /api/v1/admin/blacklist}
 * chỉ dành cho ADMIN (quy tắc phân quyền nằm ở cấu hình bảo mật chung).
 */
@RestController
@Tag(name = "Blacklist")
public class BlacklistController {

    private final BlacklistService blacklistService;

    public BlacklistController(BlacklistService blacklistService) {
        this.blacklistService = blacklistService;
    }

    /** Thêm một số vào danh sách đen. */
    @Schema(name = "BlacklistAddRequest")
    public record AddRequest(String phoneNumber, String reason) {
    }

    /** Sửa một dòng; trường nào không gửi thì giữ nguyên. */
    @Schema(name = "BlacklistUpdateRequest")
    public record UpdateRequest(String reason, Boolean active) {
    }

    /** Tra cứu một số điện thoại có đang nằm trong danh sách đen không. */
    @GetMapping("/api/v1/blacklist/lookup")
    @Operation(summary = "Check whether a phone number is blacklisted")
    public BlacklistService.Lookup lookup(@RequestParam String phoneNumber) {
        return blacklistService.lookup(phoneNumber);
    }

    @GetMapping("/api/v1/admin/blacklist")
    @Operation(summary = "Admin: list blacklist entries, newest first")
    public PageResponse<BlacklistResponse> list(@RequestParam(required = false) String query,
            @RequestParam(required = false) Boolean active,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return blacklistService.search(query, active, page, size);
    }

    @PostMapping("/api/v1/admin/blacklist")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Admin: add a phone number to the blacklist")
    public BlacklistResponse add(@AuthenticationPrincipal Jwt jwt, @RequestBody AddRequest request) {
        return blacklistService.add(UUID.fromString(jwt.getSubject()), request.phoneNumber(), request.reason());
    }

    @PatchMapping("/api/v1/admin/blacklist/{id}")
    @Operation(summary = "Admin: change the reason of an entry or switch it on or off")
    public BlacklistResponse update(@PathVariable UUID id, @RequestBody UpdateRequest request) {
        return blacklistService.update(id, request.reason(), request.active());
    }

    @DeleteMapping("/api/v1/admin/blacklist/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Operation(summary = "Admin: remove an entry from the blacklist")
    public void delete(@PathVariable UUID id) {
        blacklistService.delete(id);
    }
}
