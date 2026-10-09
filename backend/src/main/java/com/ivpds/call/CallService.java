package com.ivpds.call;

import com.ivpds.audio.AudioFile;
import com.ivpds.audio.AudioFileRepository;
import com.ivpds.audio.AudioFormat;
import com.ivpds.audio.AudioStorage;
import com.ivpds.common.PageResponse;
import com.ivpds.common.PhoneNumbers;
import com.ivpds.common.error.ApiException;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

/** Nghiệp vụ cuộc gọi: nhận cuộc gọi kèm audio, liệt kê, xem chi tiết và tải audio. */
@Service
public class CallService {

    private static final Logger log = LoggerFactory.getLogger(CallService.class);
    private static final int MAX_PAGE_SIZE = 100;
    private static final int MAX_FILENAME_LENGTH = 255;

    private final CallRecordRepository calls;
    private final AudioFileRepository audioFiles;
    private final AudioStorage storage;
    private final TransactionTemplate transaction;

    public CallService(CallRecordRepository calls, AudioFileRepository audioFiles, AudioStorage storage,
            PlatformTransactionManager transactionManager) {
        this.calls = calls;
        this.audioFiles = audioFiles;
        this.storage = storage;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    /**
     * Nhận một cuộc gọi mới: kiểm tra file, lưu audio vào kho lưu trữ, rồi ghi cuộc gọi và metadata
     * của audio vào database trong một transaction.
     *
     * <p>Kho lưu trữ và database không dùng chung transaction được, nên nếu bước ghi database thất
     * bại thì object vừa tải lên sẽ bị xóa lại, tránh để lại file không ai tham chiếu.
     */
    public CallResponse create(UUID userId, MultipartFile file, String callerNumber, Instant calledAt,
            CallSource source) {
        if (file == null || file.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "EMPTY_AUDIO", "The audio file is empty.");
        }
        String normalizedCaller = normalizeCaller(callerNumber);
        Inspection inspection = inspect(file);
        AudioFormat format = AudioFormat.detect(file.getOriginalFilename(), inspection.header());

        // Khóa object do server sinh ra; không có dữ liệu nào của client (kể cả tên file) nằm trong khóa.
        String key = "calls/%s/%s.%s".formatted(userId, UUID.randomUUID(), format.extension());
        storage.put(key, file, file.getSize(), format.contentType());

        try {
            return transaction.execute(status -> {
                CallRecord call = calls.save(new CallRecord(userId, normalizedCaller, calledAt, source));
                AudioFile audio = audioFiles.save(new AudioFile(call.getId(), storage.bucket(), key,
                        cleanFilename(file.getOriginalFilename()), format.contentType(), file.getSize(),
                        inspection.sha256()));
                return CallResponse.from(call, audio);
            });
        } catch (RuntimeException e) {
            log.warn("Saving call metadata failed; removing uploaded object {}", key);
            storage.deleteQuietly(key);
            throw e;
        }
    }

    /**
     * Danh sách cuộc gọi của người dùng, mới nhất trước, có phân trang.
     * Giá trị phân trang không hợp lệ được đưa về giới hạn cho phép thay vì báo lỗi.
     */
    @Transactional(readOnly = true)
    public PageResponse<CallResponse> list(UUID userId, int page, int size) {
        int safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
        Page<CallRecord> result = calls.findByUserIdOrderByCreatedAtDesc(userId,
                PageRequest.of(Math.max(page, 0), safeSize));
        // Lấy audio của cả trang trong một truy vấn rồi ghép theo id cuộc gọi.
        List<UUID> ids = result.getContent().stream().map(CallRecord::getId).toList();
        Map<UUID, AudioFile> audioByCall = audioFiles.findByCallRecordIdIn(ids).stream()
                .collect(Collectors.toMap(AudioFile::getCallRecordId, Function.identity()));
        return PageResponse.of(result, call -> CallResponse.from(call, audioByCall.get(call.getId())));
    }

    /** Chi tiết một cuộc gọi của chính người dùng. */
    @Transactional(readOnly = true)
    public CallResponse get(UUID userId, UUID callId) {
        CallRecord call = ownedCall(userId, callId);
        return CallResponse.from(call, audioFiles.findByCallRecordId(callId).orElse(null));
    }

    /**
     * Mở audio của một cuộc gọi thuộc về chính người dùng để tải về. Người gọi phải đóng luồng.
     * Nếu metadata còn nhưng object đã mất khỏi kho lưu trữ thì trả 404 AUDIO_OBJECT_MISSING
     * và ghi log lỗi.
     */
    public AudioDownload openAudio(UUID userId, UUID callId) {
        ownedCall(userId, callId);
        AudioFile audio = audioFiles.findByCallRecordId(callId).orElseThrow(CallService::notFound);
        ResponseInputStream<GetObjectResponse> content = storage.open(audio.getObjectKey()).orElseThrow(() -> {
            log.error("Audio {} of call {} is missing from object storage (key {})", audio.getId(), callId,
                    audio.getObjectKey());
            return new ApiException(HttpStatus.NOT_FOUND, "AUDIO_OBJECT_MISSING",
                    "The audio file of this call is no longer available.");
        });
        return new AudioDownload(content, audio.getContentType(), audio.getSizeBytes(), audio.getOriginalFilename());
    }

    /** Nội dung audio kèm thông tin cần thiết để trả về cho client. */
    public record AudioDownload(InputStream content, String contentType, long sizeBytes, String filename) {
    }

    /**
     * Tìm cuộc gọi thuộc về người dùng. Cuộc gọi của người khác được báo là không tìm thấy,
     * để không lộ việc nó có tồn tại.
     */
    private CallRecord ownedCall(UUID userId, UUID callId) {
        return calls.findByIdAndUserId(callId, userId).orElseThrow(CallService::notFound);
    }

    private static ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "CALL_NOT_FOUND", "Call not found.");
    }

    /** Chuẩn hóa số người gọi; trả 400 nếu không phải số điện thoại hợp lệ. */
    private static String normalizeCaller(String callerNumber) {
        try {
            return PhoneNumbers.normalize(callerNumber);
        } catch (IllegalArgumentException e) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PHONE_NUMBER",
                    "callerNumber must contain 6 to 15 digits, optionally starting with +.");
        }
    }

    /** Kết quả kiểm tra file upload: các byte đầu và SHA-256 của toàn bộ file. */
    private record Inspection(byte[] header, String sha256) {
    }

    /** Đọc file upload một lượt để tính SHA-256 của toàn bộ file và lấy các byte đầu dùng nhận dạng định dạng. */
    private static Inspection inspect(MultipartFile file) {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is not available", e);
        }
        byte[] header = new byte[AudioFormat.HEADER_LENGTH];
        int headerLength = 0;
        byte[] buffer = new byte[8192];
        try (InputStream in = file.getInputStream()) {
            int read;
            while ((read = in.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
                int copy = Math.min(read, header.length - headerLength);
                if (copy > 0) {
                    System.arraycopy(buffer, 0, header, headerLength, copy);
                    headerLength += copy;
                }
            }
        } catch (IOException e) {
            throw new UncheckedIOException("Could not read the uploaded file", e);
        }
        return new Inspection(Arrays.copyOf(header, headerLength), HexFormat.of().formatHex(digest.digest()));
    }

    /** Làm sạch tên file của client: chỉ giữ tên file (bỏ đường dẫn), bỏ ký tự điều khiển, giới hạn độ dài. */
    private static String cleanFilename(String original) {
        if (original == null) {
            return null;
        }
        String name = original.substring(Math.max(original.lastIndexOf('/'), original.lastIndexOf('\\')) + 1)
                .replaceAll("\\p{Cntrl}", "")
                .trim();
        if (name.isEmpty()) {
            return null;
        }
        return name.length() > MAX_FILENAME_LENGTH ? name.substring(name.length() - MAX_FILENAME_LENGTH) : name;
    }
}
