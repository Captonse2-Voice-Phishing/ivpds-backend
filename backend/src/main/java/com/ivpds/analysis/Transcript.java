package com.ivpds.analysis;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** Văn bản AI service nhận dạng được từ audio của một lần phân tích (bảng {@code transcripts}). */
@Entity
@Table(name = "transcripts")
public class Transcript {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "analysis_id", nullable = false, updatable = false)
    private UUID analysisId;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    @Column(nullable = false, length = 10)
    private String language;

    /** Tên model speech-to-text đã tạo ra transcript này. */
    @Column(name = "stt_model", length = 100)
    private String sttModel;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** Constructor rỗng dành cho JPA. */
    protected Transcript() {
    }

    public Transcript(UUID analysisId, String content, String language, String sttModel) {
        this.analysisId = analysisId;
        this.content = content;
        this.language = language;
        this.sttModel = sttModel;
        this.createdAt = Instant.now();
    }

    public UUID getAnalysisId() {
        return analysisId;
    }

    public String getContent() {
        return content;
    }

    public String getLanguage() {
        return language;
    }

    public String getSttModel() {
        return sttModel;
    }
}
