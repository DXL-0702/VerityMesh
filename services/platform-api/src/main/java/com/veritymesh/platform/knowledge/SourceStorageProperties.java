package com.veritymesh.platform.knowledge;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Runtime configuration for the Source Zone adapter.
 *
 * <p>The application is fail-closed by default. An S3-compatible client is
 * created only when {@code enabled} is true and all credentials are present.
 * Production credentials must be injected by the deployment secret manager;
 * they are never committed to application properties.</p>
 */
@ConfigurationProperties(prefix = "veritymesh.source-storage")
public class SourceStorageProperties {

    private boolean enabled;
    private String endpoint = "http://localhost:19000";
    private String region = "us-east-1";
    private String bucket = "veritymesh-source";
    private String accessKey = "";
    private String secretKey = "";
    private Duration presignDuration = Duration.ofMinutes(15);
    private String pathPrefix = "source-zone";
    private boolean forcePathStyle = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public String getBucket() {
        return bucket;
    }

    public void setBucket(String bucket) {
        this.bucket = bucket;
    }

    public String getAccessKey() {
        return accessKey;
    }

    public void setAccessKey(String accessKey) {
        this.accessKey = accessKey;
    }

    public String getSecretKey() {
        return secretKey;
    }

    public void setSecretKey(String secretKey) {
        this.secretKey = secretKey;
    }

    public Duration getPresignDuration() {
        return presignDuration;
    }

    public void setPresignDuration(Duration presignDuration) {
        this.presignDuration = presignDuration;
    }

    public String getPathPrefix() {
        return pathPrefix;
    }

    public void setPathPrefix(String pathPrefix) {
        this.pathPrefix = pathPrefix;
    }

    public boolean isForcePathStyle() {
        return forcePathStyle;
    }

    public void setForcePathStyle(boolean forcePathStyle) {
        this.forcePathStyle = forcePathStyle;
    }
}
