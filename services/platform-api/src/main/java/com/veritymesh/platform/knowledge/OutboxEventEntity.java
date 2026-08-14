package com.veritymesh.platform.knowledge;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "outbox_events")
public class OutboxEventEntity {

    @Id
    @Column(length = 256, nullable = false)
    private String id;

    @Column(name = "aggregate_type", length = 128, nullable = false)
    private String aggregateType;

    @Column(name = "aggregate_id", length = 256, nullable = false)
    private String aggregateId;

    @Column(name = "event_type", length = 128, nullable = false)
    private String eventType;

    @Column(name = "schema_version", length = 16, nullable = false)
    private String schemaVersion;

    @Column(name = "idempotency_key", length = 256, nullable = false)
    private String idempotencyKey;

    @Lob
    @Column(nullable = false, columnDefinition = "json")
    private String payload;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(name = "published_at")
    private Instant publishedAt;

    protected OutboxEventEntity() {
    }

    public OutboxEventEntity(
            String id,
            String aggregateType,
            String aggregateId,
            String eventType,
            String schemaVersion,
            String idempotencyKey,
            String payload,
            Instant occurredAt) {
        this.id = id;
        this.aggregateType = aggregateType;
        this.aggregateId = aggregateId;
        this.eventType = eventType;
        this.schemaVersion = schemaVersion;
        this.idempotencyKey = idempotencyKey;
        this.payload = payload;
        this.occurredAt = occurredAt;
    }

    public String getId() {
        return id;
    }

    public String getAggregateId() {
        return aggregateId;
    }

    public String getEventType() {
        return eventType;
    }

    public String getSchemaVersion() {
        return schemaVersion;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public String getPayload() {
        return payload;
    }

    public Instant getOccurredAt() {
        return occurredAt;
    }

    public Instant getPublishedAt() {
        return publishedAt;
    }

    public void markPublished(Instant publishedAt) {
        this.publishedAt = Objects.requireNonNull(publishedAt, "publishedAt must not be null");
    }
}
