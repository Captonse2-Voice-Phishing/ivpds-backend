package com.ivpds.audio;

import com.ivpds.common.error.ApiException;
import java.util.Arrays;
import java.util.Locale;
import java.util.Optional;
import org.springframework.http.HttpStatus;

/**
 * Các định dạng audio được phép upload. Một file được chấp nhận khi đuôi file nằm trong danh sách
 * này và các byte đầu của file đúng với định dạng đó; nhờ vậy file bị đặt sai đuôi bị loại sớm.
 * Việc giải mã đầy đủ (codec, sample rate) do FFmpeg bên AI service kiểm tra sau.
 */
public enum AudioFormat {
    MP3("mp3", "audio/mpeg"),
    WAV("wav", "audio/wav"),
    M4A("m4a", "audio/mp4"),
    AAC("aac", "audio/aac"),
    OGG("ogg", "audio/ogg"),
    WEBM("webm", "audio/webm"),
    THREE_GP("3gp", "audio/3gpp"),
    AMR("amr", "audio/amr"),
    FLAC("flac", "audio/flac");

    /** Số byte đầu cần đọc, đủ để nhận ra mọi định dạng được hỗ trợ. */
    public static final int HEADER_LENGTH = 12;

    private final String extension;
    private final String contentType;

    AudioFormat(String extension, String contentType) {
        this.extension = extension;
        this.contentType = contentType;
    }

    /** Đuôi file (không có dấu chấm). */
    public String extension() {
        return extension;
    }

    /** Content type chuẩn của định dạng; dùng thay cho content type do client gửi. */
    public String contentType() {
        return contentType;
    }

    /**
     * Xác định định dạng của file upload.
     *
     * @param filename tên file do client gửi
     * @param header   {@link #HEADER_LENGTH} byte đầu của file (ít hơn nếu file ngắn hơn)
     * @throws ApiException 415 UNSUPPORTED_AUDIO_FORMAT nếu đuôi file không được hỗ trợ,
     *                      415 INVALID_AUDIO_CONTENT nếu nội dung không khớp với đuôi file
     */
    public static AudioFormat detect(String filename, byte[] header) {
        AudioFormat format = fromFilename(filename).orElseThrow(() -> new ApiException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_AUDIO_FORMAT",
                "Unsupported audio format. Supported: mp3, wav, m4a, aac, ogg, webm, 3gp, amr, flac."));
        if (!format.matches(header)) {
            throw new ApiException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "INVALID_AUDIO_CONTENT",
                    "The file content is not valid " + format.extension + " audio.");
        }
        return format;
    }

    /** Tìm định dạng theo đuôi file (phần sau dấu chấm cuối cùng, không phân biệt hoa thường). */
    private static Optional<AudioFormat> fromFilename(String filename) {
        if (filename == null) {
            return Optional.empty();
        }
        int dot = filename.lastIndexOf('.');
        if (dot < 0) {
            return Optional.empty();
        }
        String ext = filename.substring(dot + 1).toLowerCase(Locale.ROOT);
        return Arrays.stream(values()).filter(f -> f.extension.equals(ext)).findFirst();
    }

    /** Kiểm tra các byte đầu của file có đúng dấu hiệu nhận dạng (magic bytes) của định dạng này không. */
    private boolean matches(byte[] h) {
        return switch (this) {
            case MP3 -> startsWith(h, 0, "ID3") || isMpegFrameSync(h);
            case WAV -> startsWith(h, 0, "RIFF") && startsWith(h, 8, "WAVE");
            case M4A, THREE_GP -> startsWith(h, 4, "ftyp");
            case AAC -> isAdtsSync(h) || startsWith(h, 0, "ADIF");
            case OGG -> startsWith(h, 0, "OggS");
            case WEBM -> h.length >= 4 && (h[0] & 0xFF) == 0x1A && (h[1] & 0xFF) == 0x45 && (h[2] & 0xFF) == 0xDF
                    && (h[3] & 0xFF) == 0xA3;
            case AMR -> startsWith(h, 0, "#!AMR");
            case FLAC -> startsWith(h, 0, "fLaC");
        };
    }

    /** Kiểm tra mảng byte có chứa chuỗi ASCII cho trước tại vị trí {@code offset} hay không. */
    private static boolean startsWith(byte[] h, int offset, String ascii) {
        if (h.length < offset + ascii.length()) {
            return false;
        }
        for (int i = 0; i < ascii.length(); i++) {
            if (h[offset + i] != (byte) ascii.charAt(i)) {
                return false;
            }
        }
        return true;
    }

    /** Header của khung MPEG audio: 11 bit đồng bộ đều bằng 1 và 2 bit layer khác giá trị dự trữ 00. */
    private static boolean isMpegFrameSync(byte[] h) {
        return h.length >= 2 && (h[0] & 0xFF) == 0xFF && (h[1] & 0xE0) == 0xE0 && (h[1] & 0x06) != 0;
    }

    /** Header ADTS của AAC: 12 bit đồng bộ đều bằng 1 và 2 bit layer bằng 00. */
    private static boolean isAdtsSync(byte[] h) {
        return h.length >= 2 && (h[0] & 0xFF) == 0xFF && (h[1] & 0xF6) == 0xF0;
    }
}
