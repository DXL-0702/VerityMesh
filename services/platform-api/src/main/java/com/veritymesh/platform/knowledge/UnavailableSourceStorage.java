package com.veritymesh.platform.knowledge;

/**
 * Explicit local baseline: production must provide an OSS adapter before uploads are enabled.
 */
public final class UnavailableSourceStorage implements SourceStorage {

    @Override
    public String sourceZoneKey(String projectId, String sourceObjectId, String sourceRevisionId) {
        throw new SourceStorageNotConfigured();
    }

    @Override
    public UploadReservation reserveUpload(String sourceZoneKey, String contentType, long contentLength) {
        throw new SourceStorageNotConfigured();
    }

    @Override
    public UploadedObject verifyUploaded(String sourceZoneKey) {
        throw new SourceStorageNotConfigured();
    }
}
