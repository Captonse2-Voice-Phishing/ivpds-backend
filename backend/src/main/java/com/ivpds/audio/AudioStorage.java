package com.ivpds.audio;

import com.ivpds.common.error.ApiException;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.InputStreamSource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.NoSuchBucketException;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;

/**
 * Lưu và đọc dữ liệu audio trong kho lưu trữ object tương thích S3 (MinIO).
 * Đây là nơi duy nhất trong backend làm việc trực tiếp với kho lưu trữ.
 */
@Component
public class AudioStorage implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AudioStorage.class);

    private final S3Client s3;
    private final String bucket;

    public AudioStorage(S3Client s3, StorageProperties properties) {
        this.s3 = s3;
        this.bucket = properties.bucket();
    }

    /**
     * Chạy khi ứng dụng khởi động: tạo bucket nếu chưa có.
     * Nếu không kết nối được kho lưu trữ thì ứng dụng dừng khởi động.
     */
    @Override
    public void run(ApplicationArguments args) {
        try {
            s3.headBucket(b -> b.bucket(bucket));
        } catch (NoSuchBucketException e) {
            s3.createBucket(b -> b.bucket(bucket));
            log.info("Created storage bucket {}", bucket);
        }
    }

    /** Tên bucket đang dùng. */
    public String bucket() {
        return bucket;
    }

    /**
     * Tải nội dung lên kho lưu trữ dưới khóa {@code key}.
     *
     * @param content nguồn dữ liệu mở lại được nhiều lần: client tự thử lại khi một lần gửi thất bại,
     *                và mỗi lần thử phải đọc nội dung từ đầu
     * @param size    số byte chính xác của nội dung
     * @throws ApiException 503 STORAGE_UNAVAILABLE nếu kho lưu trữ không phản hồi
     */
    public void put(String key, InputStreamSource content, long size, String contentType) {
        try {
            s3.putObject(b -> b.bucket(bucket).key(key).contentType(contentType),
                    RequestBody.fromContentProvider(() -> open(content), size, contentType));
        } catch (SdkException e) {
            throw unavailable(e);
        }
    }

    /** Mở luồng đọc mới từ nguồn dữ liệu cho một lần gửi. */
    private static InputStream open(InputStreamSource content) {
        try {
            return content.getInputStream();
        } catch (IOException e) {
            throw new UncheckedIOException("Could not read the content to upload", e);
        }
    }

    /**
     * Mở object để đọc. Người gọi phải đóng luồng sau khi dùng.
     *
     * @return rỗng nếu object không còn tồn tại trong kho lưu trữ
     * @throws ApiException 503 STORAGE_UNAVAILABLE nếu kho lưu trữ không phản hồi
     */
    public Optional<ResponseInputStream<GetObjectResponse>> open(String key) {
        try {
            return Optional.of(s3.getObject(b -> b.bucket(bucket).key(key)));
        } catch (NoSuchKeyException e) {
            return Optional.empty();
        } catch (SdkException e) {
            throw unavailable(e);
        }
    }

    /**
     * Xóa object để hoàn tác một lần upload. Chỉ cố gắng hết mức: nếu xóa thất bại thì ghi log
     * chứ không ném lỗi, để không che mất lỗi gốc.
     */
    public void deleteQuietly(String key) {
        try {
            s3.deleteObject(b -> b.bucket(bucket).key(key));
        } catch (SdkException e) {
            log.error("Could not delete orphaned object {}/{}", bucket, key, e);
        }
    }

    /** Ghi log lỗi của kho lưu trữ và chuyển thành lỗi 503 cho client. */
    private static ApiException unavailable(SdkException cause) {
        log.error("Object storage request failed", cause);
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "STORAGE_UNAVAILABLE",
                "Audio storage is temporarily unavailable.");
    }
}
