package com.veritymesh.platform.knowledge;

import java.time.Instant;

public interface SourceStorage {

    String sourceZoneKey(String projectId, String sourceObjectId, String sourceRevisionId);

    UploadReservation reserveUpload(String sourceZoneKey, String contentType, long contentLength);

    UploadedObject verifyUploaded(String sourceZoneKey);

    /**
     * Releases provider client resources when the adapter is managed by Spring.
     * Stateless implementations do not need to override this method.
     */
    default void close() {
    }

    record UploadReservation(String uploadUrl, Instant expiresAt) {
    }

    record UploadedObject(String contentSha256, String contentType, long contentLength) {
    }
}
