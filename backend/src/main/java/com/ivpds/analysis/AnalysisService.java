package com.ivpds.analysis;

import com.ivpds.audio.AudioFileRepository;
import com.ivpds.call.CallCreatedEvent;
import com.ivpds.call.CallRecordRepository;
import com.ivpds.call.CallSource;
import com.ivpds.common.error.ApiException;
import jakarta.annotation.PreDestroy;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Nghiệp vụ phân tích cuộc gọi: nhận yêu cầu phân tích, xếp hàng xử lý ở luồng nền, và trả trạng thái cùng
 * kết quả cho chủ cuộc gọi.
 *
 * <p>Phân tích chạy bất đồng bộ vì nhận dạng giọng nói có thể mất nhiều phút: yêu cầu trả về ngay với trạng
 * thái PENDING, client hỏi lại để biết kết quả. Hàng đợi nằm trong bộ nhớ của một tiến trình backend; khi
 * backend khởi động lại, các lần phân tích dang dở được đánh dấu thất bại để người dùng yêu cầu lại.
 */
@Service
public class AnalysisService implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AnalysisService.class);

    static final String INTERRUPTED = "ANALYSIS_INTERRUPTED";
    static final String QUEUE_FULL = "ANALYSIS_QUEUE_FULL";
    private static final List<Analysis.Status> ACTIVE = List.of(Analysis.Status.PENDING, Analysis.Status.PROCESSING);

    private final AnalysisRepository analyses;
    private final TranscriptRepository transcripts;
    private final RiskResultRepository riskResults;
    private final CallRecordRepository calls;
    private final AudioFileRepository audioFiles;
    private final AnalysisProcessor processor;
    private final AnalysisProperties properties;
    private final TransactionTemplate transaction;
    private final ThreadPoolTaskExecutor executor;

    public AnalysisService(AnalysisRepository analyses, TranscriptRepository transcripts,
            RiskResultRepository riskResults, CallRecordRepository calls, AudioFileRepository audioFiles,
            AnalysisProcessor processor, AnalysisProperties properties,
            PlatformTransactionManager transactionManager) {
        this.analyses = analyses;
        this.transcripts = transcripts;
        this.riskResults = riskResults;
        this.calls = calls;
        this.audioFiles = audioFiles;
        this.processor = processor;
        this.properties = properties;
        this.transaction = new TransactionTemplate(transactionManager);
        // Bộ thực thi riêng của module, không đăng ký làm bean để không thay thế bộ thực thi mặc định của Spring.
        this.executor = new ThreadPoolTaskExecutor();
        this.executor.setThreadNamePrefix("analysis-");
        this.executor.setCorePoolSize(properties.workers());
        this.executor.setMaxPoolSize(properties.workers());
        this.executor.setQueueCapacity(properties.queueCapacity());
        this.executor.initialize();
    }

    /**
     * Chạy khi backend khởi động: các lần phân tích còn PENDING hoặc PROCESSING là của lần chạy trước và sẽ
     * không bao giờ được xử lý tiếp, nên đánh dấu chúng thất bại.
     */
    @Override
    public void run(ApplicationArguments args) {
        Integer count = transaction.execute(status -> analyses.failUnfinished(INTERRUPTED,
                "The analysis was interrupted by a restart. Please request it again.", Instant.now()));
        if (count != null && count > 0) {
            log.warn("Marked {} unfinished analyses as failed after a restart", count);
        }
    }

    /** Dừng bộ thực thi khi backend tắt; các lần phân tích đang chạy sẽ được đánh dấu thất bại ở lần khởi động sau. */
    @PreDestroy
    void shutdown() {
        executor.shutdown();
    }

    /**
     * Yêu cầu phân tích một cuộc gọi của chính người dùng.
     *
     * @throws ApiException 404 nếu không có cuộc gọi đó, 409 nếu cuộc gọi không có audio hoặc đang được phân
     *                      tích, 503 nếu hàng đợi đã đầy
     */
    public AnalysisResponse start(UUID userId, UUID callId) {
        requireOwnedCall(userId, callId);
        return toResponse(enqueue(callId));
    }

    /**
     * Tự bắt đầu phân tích khi một cuộc gọi vừa được gửi lên (nếu cấu hình cho phép). Lỗi ở đây không được làm
     * hỏng việc gửi cuộc gọi, nên chỉ ghi log; người dùng vẫn có thể yêu cầu phân tích lại sau.
     */
    @EventListener
    public void onCallCreated(CallCreatedEvent event) {
        // Cuộc gọi trực tiếp được phân tích ngay trên luồng âm thanh, và lúc này chưa có file để phân tích.
        if (!properties.autoStart() || event.source() == CallSource.LIVE) {
            return;
        }
        try {
            enqueue(event.callId());
        } catch (RuntimeException e) {
            log.warn("Could not start the analysis of call {} automatically: {}", event.callId(), e.getMessage());
        }
    }

    /** Lần phân tích mới nhất của một cuộc gọi thuộc về người dùng. */
    @Transactional(readOnly = true)
    public AnalysisResponse latest(UUID userId, UUID callId) {
        requireOwnedCall(userId, callId);
        return analyses.findFirstByCallRecordIdOrderByCreatedAtDesc(callId)
                .map(this::toResponse)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ANALYSIS_NOT_FOUND",
                        "This call has not been analysed yet."));
    }

    /** Mọi lần phân tích của một cuộc gọi thuộc về người dùng, mới nhất trước. */
    @Transactional(readOnly = true)
    public List<AnalysisResponse> list(UUID userId, UUID callId) {
        requireOwnedCall(userId, callId);
        return analyses.findByCallRecordIdOrderByCreatedAtDesc(callId).stream().map(this::toResponse).toList();
    }

    /** Tạo một lần phân tích PENDING rồi đưa vào hàng đợi xử lý. */
    private Analysis enqueue(UUID callId) {
        if (audioFiles.findByCallRecordId(callId).isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, AnalysisProcessor.NO_AUDIO,
                    AnalysisProcessor.messageFor(AnalysisProcessor.NO_AUDIO));
        }
        Analysis analysis;
        try {
            analysis = transaction.execute(status -> {
                if (analyses.existsByCallRecordIdAndStatusIn(callId, ACTIVE)) {
                    throw inProgress();
                }
                return analyses.saveAndFlush(new Analysis(callId));
            });
        } catch (DataIntegrityViolationException e) {
            // Hai yêu cầu cùng lúc: chỉ mục duy nhất trong database chặn yêu cầu thứ hai.
            throw inProgress();
        }
        UUID analysisId = analysis.getId();
        try {
            // Đưa vào hàng đợi sau khi transaction đã commit, để luồng xử lý đọc được dòng vừa tạo.
            executor.execute(() -> processor.process(analysisId));
        } catch (TaskRejectedException e) {
            String message = "Too many analyses are waiting. Please try again later.";
            transaction.executeWithoutResult(status -> analyses.findById(analysisId)
                    .ifPresent(pending -> pending.fail(QUEUE_FULL, message)));
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, QUEUE_FULL, message);
        }
        return analysis;
    }

    private static ApiException inProgress() {
        return new ApiException(HttpStatus.CONFLICT, "ANALYSIS_IN_PROGRESS",
                "This call is already being analysed.");
    }

    /** Cuộc gọi của người khác được báo là không tìm thấy, để không lộ việc nó có tồn tại. */
    private void requireOwnedCall(UUID userId, UUID callId) {
        if (calls.findByIdAndUserId(callId, userId).isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "CALL_NOT_FOUND", "Call not found.");
        }
    }

    private AnalysisResponse toResponse(Analysis analysis) {
        return AnalysisResponse.from(analysis, transcripts.findByAnalysisId(analysis.getId()).orElse(null),
                riskResults.findByAnalysisId(analysis.getId()).orElse(null));
    }
}
