package com.veritymesh.platform.knowledge;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "source_objects")
public class SourceObjectEntity {

    @Id
    @Column(length = 256, nullable = false)
    private String id;

    @Column(name = "project_id", length = 256, nullable = false)
    private String projectId;

    @Column(name = "source_kind", length = 64, nullable = false)
    private String sourceKind;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected SourceObjectEntity() {
    }

    public SourceObjectEntity(String id, String projectId, String sourceKind, Instant createdAt) {
        this.id = id;
        this.projectId = projectId;
        this.sourceKind = sourceKind;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }
}
