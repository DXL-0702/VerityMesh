package com.veritymesh.platform.knowledge;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "processing_tasks")
public class ProcessingTaskEntity {

    @Id
    @Column(length = 256, nullable = false)
    private String id;

    @Column(name = "source_revision_id", length = 256, nullable = false)
    private String sourceRevisionId;

    @Enumerated(EnumType.STRING)
    @Column(length = 32, nullable = false)
    private SourceRevisionStatus status;

    @Column(nullable = false)
    private int progress;

    @Column(nullable = false)
    private int attempt;

    @Column(name = "failure_code", length = 128)
    private String failureCode;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected ProcessingTaskEntity() {
    }

    public ProcessingTaskEntity(
            String id,
            String sourceRevisionId,
            SourceRevisionStatus status,
            int progress,
            int attempt,
            Instant updatedAt) {
        this.id = id;
        this.sourceRevisionId = sourceRevisionId;
        this.status = status;
        this.progress = progress;
        this.attempt = attempt;
        this.updatedAt = updatedAt;
    }

    public String getId() {
        return id;
    }

    public String getSourceRevisionId() {
        return sourceRevisionId;
    }

    public SourceRevisionStatus getStatus() {
        return status;
    }

    public int getProgress() {
        return progress;
    }

    public String getFailureCode() {
        return failureCode;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void markQueued(Instant queuedAt) {
        this.status = SourceRevisionStatus.QUEUED;
        this.progress = 0;
        this.attempt = 0;
        this.updatedAt = queuedAt;
    }
}
