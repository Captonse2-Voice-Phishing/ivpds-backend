package com.ivpds.analysis;

import com.ivpds.analysis.AiClient.RiskAssessment;
import com.ivpds.audio.AudioFile;
import com.ivpds.audio.AudioFileRepository;
import com.ivpds.audio.AudioStorage;
import com.ivpds.call.CallCreatedEvent;
import com.ivpds.call.CallRecord;
import com.ivpds.call.CallRecordRepository;
import com.ivpds.call.CallSource;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.core.io.FileSystemResource;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Ghi dữ liệu của cuộc gọi trực tiếp vào database và kho lưu trữ: mở cuộc gọi, lưu ghi âm, lưu kết quả hoặc lỗi.
 * Kết quả được ghi vào đúng các bảng mà phân tích file dùng, nên mọi API xem lịch sử và kết quả đều dùng chung.
 */
@Component
public class LiveCallRecorder {

    private static final Logger log = LoggerFactory.getLogger(LiveCallRecorder.class);

    private final CallRecordRepository calls;
    private final AudioFileRepository audioFiles;
    private final AnalysisRepository analyses;
    private final TranscriptRepository transcripts;
    private final RiskResultRepository riskResults;
    private final AudioStorage storage;
    private final TransactionTemplate transaction;
    private final ApplicationEventPublisher events;

    public LiveCallRecorder(CallRecordRepository calls, AudioFileRepository audioFiles, AnalysisRepository analyses,
            TranscriptRepository transcripts, RiskResultRepository riskResults, AudioStorage storage,
            PlatformTransactionManager transactionManager, ApplicationEventPublisher events) {
        this.events = events;
        this.calls = calls;
        this.audioFiles = audioFiles;
        this.analyses = analyses;
        this.transcripts = transcripts;
        this.riskResults = riskResults;
        this.storage = storage;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    /** Cuộc gọi và lần phân tích vừa mở. */
    public record Opened(UUID callId, UUID analysisId) {
    }

    /** Tạo bản ghi cuộc gọi nguồn LIVE và một lần phân tích ở trạng thái PROCESSING. */
    public Opened open(UUID userId, String normalizedCallerNumber) {
        Opened opened = transaction.execute(status -> {
            CallRecord call = calls.save(new CallRecord(userId, normalizedCallerNumber, Instant.now(),
                    CallSource.LIVE));
            Analysis analysis = new Analysis(call.getId());
            analysis.start();
            return new Opened(call.getId(), analyses.save(analysis).getId());
        });
        // Cùng sự kiện với cuộc gọi gửi file, để cảnh báo blacklist hoạt động ngay khi cuộc gọi bắt đầu.
        events.publishEvent(new CallCreatedEvent(opened.callId(), userId, normalizedCallerNumber, CallSource.LIVE));
        return opened;
    }

    /**
     * Lưu ghi âm của cuộc gọi (file WAV) vào kho lưu trữ và ghi metadata. Việc lưu ghi âm không được làm hỏng
     * kết quả phân tích: nếu thất bại thì chỉ ghi log, cuộc gọi vẫn có transcript và điểm rủi ro.
     */
    public void storeAudio(UUID userId, UUID callId, Path wav, long sizeBytes, String sha256, double seconds) {
        String key = "calls/%s/%s.wav".formatted(userId, UUID.randomUUID());
        try {
            storage.put(key, new FileSystemResource(wav), sizeBytes, "audio/wav");
        } catch (RuntimeException e) {
            log.error("Could not store the recording of live call {}", callId, e);
            return;
        }
        try {
            transaction.executeWithoutResult(status -> {
                AudioFile audio = new AudioFile(callId, storage.bucket(), key, "live-call.wav", "audio/wav",
                        sizeBytes, sha256);
                audio.setDurationSeconds(BigDecimal.valueOf(seconds).setScale(3, RoundingMode.HALF_UP));
                audioFiles.save(audio);
            });
        } catch (RuntimeException e) {
            log.error("Could not save the audio metadata of live call {}; removing object {}", callId, key, e);
            storage.deleteQuietly(key);
        }
    }

    /** Lưu transcript và kết quả rủi ro cuối cùng, đánh dấu hoàn tất. */
    public void complete(UUID analysisId, String transcript, String sttModel, RiskAssessment risk) {
        BigDecimal probability = risk.components() == null || risk.components().modelProbability() == null
                ? null : BigDecimal.valueOf(risk.components().modelProbability()).setScale(6, RoundingMode.HALF_UP);
        UUID callId = transaction.execute(status -> {
            transcripts.save(new Transcript(analysisId, transcript, "vi", truncate(sttModel, 100)));
            riskResults.save(new RiskResult(analysisId, risk.riskScore(), RiskResult.Level.valueOf(risk.riskLevel()),
                    BigDecimal.valueOf(risk.confidence()).setScale(4, RoundingMode.HALF_UP), probability,
                    risk.indicators(), truncate(risk.modelVersion(), 100), truncate(risk.rulesetVersion(), 30),
                    truncate(risk.riskEngineVersion(), 30)));
            Analysis analysis = analyses.findById(analysisId).orElseThrow();
            analysis.complete();
            return analysis.getCallRecordId();
        });
        AnalysisProcessor.publishCompleted(events, analysisId, callId, risk);
    }

    /**
     * Đánh dấu lần phân tích thất bại kèm mã lỗi; giữ lại transcript nếu đã có.
     *
     * @param transcript phần hội thoại đã nhận dạng được trước khi lỗi, hoặc null
     */
    public void fail(UUID analysisId, String code, String transcript, String sttModel) {
        try {
            transaction.executeWithoutResult(status -> analyses.findById(analysisId)
                    .filter(analysis -> !analysis.isFinished())
                    .ifPresent(analysis -> {
                        if (transcript != null && !transcript.isBlank()) {
                            transcripts.save(new Transcript(analysisId, transcript, "vi", truncate(sttModel, 100)));
                        }
                        analysis.fail(code, AnalysisProcessor.messageFor(code));
                    }));
        } catch (RuntimeException e) {
            log.error("Could not record the failure {} of live analysis {}", code, analysisId, e);
        }
    }

    private static String truncate(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }
}
