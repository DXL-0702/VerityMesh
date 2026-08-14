package com.veritymesh.platform.knowledge;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "veritymesh.outbox.publisher")
public class KafkaOutboxProperties {

    private boolean enabled;
    private String bootstrapServers = "";
    private String sourceRevisionTopic = "veritymesh.source-revision-submitted";
    private long pollIntervalMs = 1_000L;
    private int batchSize = 100;
    private Duration sendTimeout = Duration.ofSeconds(10);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getBootstrapServers() {
        return bootstrapServers;
    }

    public void setBootstrapServers(String bootstrapServers) {
        this.bootstrapServers = bootstrapServers;
    }

    public String getSourceRevisionTopic() {
        return sourceRevisionTopic;
    }

    public void setSourceRevisionTopic(String sourceRevisionTopic) {
        this.sourceRevisionTopic = sourceRevisionTopic;
    }

    public long getPollIntervalMs() {
        return pollIntervalMs;
    }

    public void setPollIntervalMs(long pollIntervalMs) {
        this.pollIntervalMs = pollIntervalMs;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public Duration getSendTimeout() {
        return sendTimeout;
    }

    public void setSendTimeout(Duration sendTimeout) {
        this.sendTimeout = sendTimeout;
    }

    public void validate() {
        if (bootstrapServers == null || bootstrapServers.isBlank()) {
            throw new IllegalStateException("Kafka bootstrapServers must be configured when publishing is enabled");
        }
        if (sourceRevisionTopic == null || sourceRevisionTopic.isBlank()) {
            throw new IllegalStateException("Kafka sourceRevisionTopic must be configured when publishing is enabled");
        }
        if (pollIntervalMs < 1) {
            throw new IllegalStateException("Kafka outbox pollIntervalMs must be positive");
        }
        if (batchSize < 1 || batchSize > 1_000) {
            throw new IllegalStateException("Kafka outbox batchSize must be between 1 and 1000");
        }
        if (sendTimeout == null || sendTimeout.isNegative() || sendTimeout.isZero()) {
            throw new IllegalStateException("Kafka outbox sendTimeout must be positive");
        }
    }
}
