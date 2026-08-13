package com.veritymesh.platform.knowledge;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "source_revisions")
public class SourceRevisionEntity {

    @Id
    @Column(length = 256, nullable = false)
    private String id;

    @Column(name = "project_id", length = 256, nullable = false)
    private String projectId;

    @Column(name = "source_object_id", length = 256, nullable = false)
    private String sourceObjectId;

    @Column(name = "revision_number", nullable = false)
    private int revisionNumber;

    @Column(length = 512, nullable = false)
    private String filename;

    @Column(name = "source_zone_key", length = 1024, nullable = false)
    private String sourceZoneKey;

    @Column(name = "content_sha256", length = 64, nullable = false)
    private String contentSha256;

    @Column(name = "content_type", length = 256, nullable = false)
    private String contentType;

    @Column(name = "content_length", nullable = false)
    private long contentLength;

    @Column(name = "idempotency_key", length = 256, nullable = false)
    private String idempotencyKey;

    @Enumerated(EnumType.STRING)
    @Column(length = 32, nullable = false)
    private SourceRevisionStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected SourceRevisionEntity() {
    }

    public SourceRevisionEntity(
            String id,
            String projectId,
            String sourceObjectId,
            int revisionNumber,
            String filename,
            String sourceZoneKey,
            String contentSha256,
            String contentType,
            long contentLength,
            String idempotencyKey,
            SourceRevisionStatus status,
            Instant createdAt) {
        this.id = id;
        this.projectId = projectId;
        this.sourceObjectId = sourceObjectId;
        this.revisionNumber = revisionNumber;
        this.filename = filename;
        this.sourceZoneKey = sourceZoneKey;
        this.contentSha256 = contentSha256;
        this.contentType = contentType;
        this.contentLength = contentLength;
        this.idempotencyKey = idempotencyKey;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getSourceObjectId() {
        return sourceObjectId;
    }

    public String getSourceZoneKey() {
        return sourceZoneKey;
    }

    public SourceRevisionStatus getStatus() {
        return status;
    }

    public void markQueued() {
        this.status = SourceRevisionStatus.QUEUED;
    }

    public String getProjectId() {
        return projectId;
    }

    public String getContentSha256() {
        return contentSha256;
    }

    public String getFilename() {
        return filename;
    }

    public String getContentType() {
        return contentType;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public long getContentLength() {
        return contentLength;
    }
}
