package com.ivpds.analysis;

import com.ivpds.analysis.AiClient.RiskAssessment;
import com.ivpds.analysis.AiClient.Transcription;
import com.ivpds.audio.AudioFile;
import com.ivpds.audio.AudioFileRepository;
import com.ivpds.audio.AudioStorage;
import com.ivpds.common.error.ApiException;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Thực hiện một lần phân tích: lấy audio từ kho lưu trữ, gọi AI service để nhận dạng giọng nói rồi đánh giá
 * rủi ro, và ghi kết quả vào database.
 *
 * <p>Các lần gọi AI service chạy ngoài transaction vì có thể kéo dài nhiều phút; mỗi lần ghi database là một
 * transaction ngắn riêng. Nếu bất kỳ bước nào thất bại, lần phân tích được đánh dấu FAILED kèm mã lỗi. Không có
 * trường hợp nào một lỗi được thay bằng kết quả rủi ro mặc định.
 */
@Component
public class AnalysisProcessor {

    private static final Logger log = LoggerFactory.getLogger(AnalysisProcessor.class);

    static final String NO_AUDIO = "CALL_HAS_NO_AUDIO";
    static final String AUDIO_OBJECT_MISSING = "AUDIO_OBJECT_MISSING";
    static final String STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE";
    static final String NO_SPEECH_DETECTED = "NO_SPEECH_DETECTED";
    static final String INTERNAL_ERROR = "INTERNAL_ERROR";

    /** Thông báo cho người dùng theo từng mã lỗi; mã không có trong bảng dùng thông báo chung. */
    private static final Map<String, String> MESSAGES = Map.ofEntries(
            Map.entry(AiServiceException.UNAVAILABLE, "The analysis service is temporarily unavailable."),
            Map.entry(AiServiceException.TIMEOUT, "The analysis took too long and was stopped."),
            Map.entry(AiServiceException.ERROR, "The analysis service reported an error."),
            Map.entry(AiServiceException.AUTH_FAILED, "The analysis service refused the request."),
            Map.entry(AiServiceException.INVALID_RESPONSE, "The analysis service returned an unusable result."),
            Map.entry(AiServiceException.REQUEST_REJECTED, "The analysis service refused the request."),
            Map.entry("STT_UNAVAILABLE", "Speech recognition is temporarily unavailable."),
            Map.entry("STT_FAILED", "Speech recognition failed for this audio."),
            Map.entry("NLP_MODEL_UNAVAILABLE", "The risk model is temporarily unavailable."),
            Map.entry("AUDIO_PROCESSING_UNAVAILABLE", "Audio processing is temporarily unavailable."),
            Map.entry("AUDIO_PROCESSING_TIMEOUT", "Audio processing took too long."),
            Map.entry("INVALID_AUDIO", "The file could not be read as audio."),
            Map.entry("EMPTY_AUDIO", "The audio file is empty."),
            Map.entry("AUDIO_TOO_LONG", "The audio is longer than the analysis service accepts."),
            Map.entry("AUDIO_TOO_LARGE", "The audio is larger than the analysis service accepts."),
            Map.entry("PAYLOAD_TOO_LARGE", "The audio is larger than the analysis service accepts."),
            Map.entry(NO_AUDIO, "This call has no audio to analyse."),
            Map.entry(AUDIO_OBJECT_MISSING, "The audio file of this call is no longer available."),
            Map.entry(STORAGE_UNAVAILABLE, "Audio storage is temporarily unavailable."),
            Map.entry(NO_SPEECH_DETECTED, "No speech was recognised in this audio."),
            Map.entry("LIVE_CALL_NOT_STARTED", "The live call was opened but its audio stream never started."),
            Map.entry("LIVE_SESSION_LIMIT", "Too many calls are being analysed right now."),
            Map.entry("LIVE_SESSION_OVERLOADED", "The live analysis could not keep up with the call."),
            Map.entry("LIVE_SESSION_FAILED", "The live analysis failed."),
            Map.entry(INTERNAL_ERROR, "The analysis failed unexpectedly."));
    private static final String DEFAULT_MESSAGE = "The analysis could not be completed.";

    private final AnalysisRepository analyses;
    private final TranscriptRepository transcripts;
    private final RiskResultRepository riskResults;
    private final AudioFileRepository audioFiles;
    private final AudioStorage storage;
    private final AiClient ai;
    private final TransactionTemplate transaction;
    private final ApplicationEventPublisher events;

    public AnalysisProcessor(AnalysisRepository analyses, TranscriptRepository transcripts,
            RiskResultRepository riskResults, AudioFileRepository audioFiles, AudioStorage storage, AiClient ai,
            PlatformTransactionManager transactionManager, ApplicationEventPublisher events) {
        this.events = events;
        this.analyses = analyses;
        this.transcripts = transcripts;
        this.riskResults = riskResults;
        this.audioFiles = audioFiles;
        this.storage = storage;
        this.ai = ai;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    /** Thông báo cho người dùng ứng với một mã lỗi. */
    static String messageFor(String code) {
        return MESSAGES.getOrDefault(code, DEFAULT_MESSAGE);
    }

    /**
     * Chạy trọn một lần phân tích đang ở trạng thái PENDING. Phương thức này không ném lỗi ra ngoài: mọi thất
     * bại đều được ghi vào chính lần phân tích đó.
     */
    public void process(UUID analysisId) {
        String requestId = analysisId.toString();
        try {
            AudioFile audio = begin(analysisId);
            if (audio == null) {
                return;
            }
            Transcription transcription = transcribe(audio, requestId);
            saveDuration(audio.getId(), transcription);
            String text = transcription.transcript().strip();
            if (text.isEmpty()) {
                throw new Failure(NO_SPEECH_DETECTED);
            }
            saveTranscript(analysisId, transcription, text);
            RiskAssessment risk = ai.assessRisk(text, requestId);
            complete(analysisId, risk);
            log.info("Analysis {} completed: {} ({})", analysisId, risk.riskLevel(), risk.riskScore());
        } catch (AiServiceException e) {
            log.warn("Analysis {} failed: {} ({})", analysisId, e.getCode(), e.getMessage());
            fail(analysisId, e.getCode());
        } catch (Failure e) {
            log.warn("Analysis {} failed: {}", analysisId, e.code);
            fail(analysisId, e.code);
        } catch (RuntimeException e) {
            log.error("Analysis {} failed unexpectedly", analysisId, e);
            fail(analysisId, INTERNAL_ERROR);
        }
    }

    /**
     * Chuyển lần phân tích sang PROCESSING và trả về file audio cần xử lý.
     *
     * @return null nếu lần phân tích không còn tồn tại hoặc không ở trạng thái PENDING (không có gì để làm)
     */
    private AudioFile begin(UUID analysisId) {
        return transaction.execute(status -> {
            Analysis analysis = analyses.findById(analysisId).orElse(null);
            if (analysis == null || analysis.getStatus() != Analysis.Status.PENDING) {
                return null;
            }
            analysis.start();
            return audioFiles.findByCallRecordId(analysis.getCallRecordId())
                    .orElseThrow(() -> new Failure(NO_AUDIO));
        });
    }

    /** Mở audio trong kho lưu trữ và gửi sang AI service; luồng đọc luôn được đóng. */
    private Transcription transcribe(AudioFile audio, String requestId) {
        InputStream content;
        try {
            content = storage.open(audio.getObjectKey()).orElseThrow(() -> new Failure(AUDIO_OBJECT_MISSING));
        } catch (ApiException e) {
            throw new Failure(STORAGE_UNAVAILABLE);
        }
        try (content) {
            String filename = audio.getOriginalFilename() != null ? audio.getOriginalFilename() : "audio";
            return ai.transcribe(content, audio.getSizeBytes(), filename, audio.getContentType(), requestId);
        } catch (IOException e) {
            // Chỉ xảy ra khi đóng luồng; kết quả nhận dạng (nếu có) đã bị bỏ qua nên coi như lỗi kho lưu trữ.
            throw new Failure(STORAGE_UNAVAILABLE);
        }
    }

    /** Lưu thời lượng audio do AI service đo; giá trị này đúng cả khi audio không có tiếng nói. */
    private void saveDuration(UUID audioId, Transcription transcription) {
        Double duration = transcription.audio() == null ? null : transcription.audio().durationSeconds();
        if (duration == null || duration < 0 || duration.isNaN() || duration.isInfinite()) {
            return;
        }
        transaction.executeWithoutResult(status -> audioFiles.findById(audioId).ifPresent(audio ->
                audio.setDurationSeconds(BigDecimal.valueOf(duration).setScale(3, RoundingMode.HALF_UP))));
    }

    /** Lưu transcript ngay khi có, để nó còn lại dù bước đánh giá rủi ro thất bại. */
    private void saveTranscript(UUID analysisId, Transcription transcription, String text) {
        String language = transcription.language() == null || transcription.language().isBlank()
                ? "vi" : transcription.language();
        transaction.executeWithoutResult(status -> transcripts.save(new Transcript(analysisId, text,
                truncate(language, 10), truncate(transcription.sttModel(), 100))));
    }

    /** Lưu kết quả đánh giá rủi ro và đánh dấu hoàn tất, trong cùng một transaction. */
    private void complete(UUID analysisId, RiskAssessment risk) {
        BigDecimal probability = risk.components() == null || risk.components().modelProbability() == null
                ? null : BigDecimal.valueOf(risk.components().modelProbability()).setScale(6, RoundingMode.HALF_UP);
        UUID callId = transaction.execute(status -> {
            riskResults.save(new RiskResult(analysisId, risk.riskScore(), RiskResult.Level.valueOf(risk.riskLevel()),
                    BigDecimal.valueOf(risk.confidence()).setScale(4, RoundingMode.HALF_UP), probability,
                    risk.indicators(), truncate(risk.modelVersion(), 100), truncate(risk.rulesetVersion(), 30),
                    truncate(risk.riskEngineVersion(), 30)));
            Analysis analysis = analyses.findById(analysisId).orElseThrow();
            analysis.complete();
            return analysis.getCallRecordId();
        });
        publishCompleted(events, analysisId, callId, risk);
    }

    /** Báo cho các module khác sau khi kết quả đã commit; lỗi của bên nghe không được làm hỏng lần phân tích. */
    static void publishCompleted(ApplicationEventPublisher events, UUID analysisId, UUID callId,
            RiskAssessment risk) {
        try {
            events.publishEvent(new AnalysisCompletedEvent(analysisId, callId,
                    RiskResult.Level.valueOf(risk.riskLevel()), risk.riskScore()));
        } catch (RuntimeException e) {
            log.error("A listener failed after analysis {} completed", analysisId, e);
        }
    }

    /** Đánh dấu thất bại. Nếu chính việc ghi này cũng lỗi thì chỉ ghi log, vì không còn gì để làm thêm. */
    private void fail(UUID analysisId, String code) {
        try {
            transaction.executeWithoutResult(status -> analyses.findById(analysisId)
                    .filter(analysis -> !analysis.isFinished())
                    .ifPresent(analysis -> analysis.fail(code, messageFor(code))));
        } catch (RuntimeException e) {
            log.error("Could not record the failure {} of analysis {}", code, analysisId, e);
        }
    }

    private static String truncate(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }

    /** Thất bại do chính backend phát hiện (không phải do AI service), kèm mã lỗi. */
    private static final class Failure extends RuntimeException {

        private final String code;

        Failure(String code) {
            super(code);
            this.code = code;
        }
    }
}
