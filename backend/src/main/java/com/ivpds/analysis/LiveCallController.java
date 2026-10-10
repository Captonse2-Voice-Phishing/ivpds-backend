package com.ivpds.analysis;

import com.ivpds.common.PhoneNumbers;
import com.ivpds.common.error.ApiException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * API mở một cuộc gọi trực tiếp (cuộc gọi VoIP trong ứng dụng được phân tích ngay khi đang diễn ra).
 *
 * <p>Trình tự: client gọi API này khi cuộc gọi bắt đầu, rồi mở WebSocket tới {@code streamPath} kèm vé nhận được,
 * gửi âm thanh của hai bên và nhận transcript, điểm rủi ro, cảnh báo trong lúc gọi. Sau khi cuộc gọi kết thúc,
 * kết quả xem lại được qua các API {@code /api/v1/calls/{callId}/analyses} như mọi cuộc gọi khác.
 */
@RestController
@RequestMapping("/api/v1/live-calls")
@Tag(name = "Live calls")
public class LiveCallController {

    static final String STREAM_PATH = "/api/v1/live-calls/stream";

    private final LiveCallRecorder recorder;
    private final LiveCallTickets tickets;

    public LiveCallController(LiveCallRecorder recorder, LiveCallTickets tickets) {
        this.recorder = recorder;
        this.tickets = tickets;
    }

    /**
     * Thông tin mở cuộc gọi trực tiếp.
     *
     * @param callerNumber số của người gọi đến, nếu biết
     */
    public record OpenRequest(String callerNumber) {
    }

    /**
     * Những gì client cần để truyền âm thanh.
     *
     * @param streamPath             đường dẫn WebSocket (cùng máy chủ với API), mở kèm tham số {@code ticket}
     * @param ticket                 vé dùng một lần
     * @param ticketExpiresInSeconds vé hết hạn sau bao nhiêu giây nếu chưa dùng
     * @param audioFormat            định dạng âm thanh phải gửi
     */
    public record OpenResponse(UUID callId, UUID analysisId, String streamPath, String ticket,
            long ticketExpiresInSeconds, AudioFormat audioFormat) {
    }

    /**
     * Định dạng âm thanh của luồng: mỗi gói nhị phân gồm một byte cho biết người nói, theo sau là mẫu PCM.
     *
     * @param speakerPrefix giá trị byte đầu của gói ứng với từng người nói
     */
    public record AudioFormat(String encoding, int sampleRate, int channels, Map<String, String> speakerPrefix) {

        static final AudioFormat PCM_16K_MONO = new AudioFormat("pcm_s16le", 16_000, 1,
                Map.of("0", "CALLER", "1", "CALLEE"));
    }

    /** Mở một cuộc gọi trực tiếp và nhận vé để truyền âm thanh. */
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Open a live call and get a one-time ticket for its audio stream")
    public OpenResponse open(@AuthenticationPrincipal Jwt jwt, @RequestBody(required = false) OpenRequest request) {
        UUID userId = UUID.fromString(jwt.getSubject());
        String caller;
        try {
            caller = PhoneNumbers.normalize(request == null ? null : request.callerNumber());
        } catch (IllegalArgumentException e) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER",
                    "callerNumber must contain 6 to 15 digits, optionally starting with +.");
        }
        // Dọn các cuộc gọi đã mở nhưng không bao giờ truyền âm thanh, để chúng không nằm mãi ở PROCESSING.
        tickets.removeExpired().forEach(expired ->
                recorder.fail(expired.analysisId(), "LIVE_CALL_NOT_STARTED", null, null));

        LiveCallRecorder.Opened opened = recorder.open(userId, caller);
        String ticket = tickets.issue(opened.callId(), opened.analysisId(), userId);
        return new OpenResponse(opened.callId(), opened.analysisId(), STREAM_PATH, ticket,
                tickets.ttl().toSeconds(), AudioFormat.PCM_16K_MONO);
    }
}
