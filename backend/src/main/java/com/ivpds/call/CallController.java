package com.ivpds.call;

import com.ivpds.call.CallService.AudioDownload;
import com.ivpds.common.PageResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** API cuộc gọi. Mọi API đều cần đăng nhập và chỉ làm việc với cuộc gọi của chính người dùng. */
@RestController
@RequestMapping("/api/v1/calls")
@Tag(name = "Calls")
public class CallController {

    private final CallService callService;

    public CallController(CallService callService) {
        this.callService = callService;
    }

    /**
     * Gửi một cuộc gọi: upload file audio (ghi âm trong ứng dụng hoặc chọn từ thiết bị) dạng
     * multipart, kèm số người gọi, thời điểm gọi và nguồn audio nếu có.
     */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Submit a call: upload its audio (recorded in the app or picked from the device)")
    public CallResponse create(@AuthenticationPrincipal Jwt jwt,
            @RequestPart("audio") MultipartFile audio,
            @RequestParam(required = false) String callerNumber,
            @RequestParam(required = false) Instant calledAt,
            @RequestParam(defaultValue = "UPLOADED") CallSource source) {
        return callService.create(userId(jwt), audio, callerNumber, calledAt, source);
    }

    /** Danh sách cuộc gọi của người dùng đang đăng nhập, mới nhất trước. */
    @GetMapping
    @Operation(summary = "List the signed-in user's calls, newest first")
    public PageResponse<CallResponse> list(@AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return callService.list(userId(jwt), page, size);
    }

    /** Chi tiết một cuộc gọi. */
    @GetMapping("/{id}")
    public CallResponse get(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        return callService.get(userId(jwt), id);
    }

    /** Tải file audio của một cuộc gọi; nội dung được truyền thẳng từ kho lưu trữ về client. */
    @GetMapping("/{id}/audio")
    @Operation(summary = "Download the audio of one of the signed-in user's calls")
    public ResponseEntity<InputStreamResource> audio(@AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        AudioDownload download = callService.openAudio(userId(jwt), id);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.parseMediaType(download.contentType()));
        headers.setContentLength(download.sizeBytes());
        headers.setContentDisposition(ContentDisposition.attachment()
                .filename(download.filename() != null ? download.filename() : "audio", StandardCharsets.UTF_8)
                .build());
        return new ResponseEntity<>(new InputStreamResource(download.content()), headers, HttpStatus.OK);
    }

    /** Lấy id người dùng từ access token. */
    private static UUID userId(Jwt jwt) {
        return UUID.fromString(jwt.getSubject());
    }
}
