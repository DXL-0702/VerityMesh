package com.veritymesh.platform.knowledge;

import java.time.Instant;

public interface SourceStorage {

    UploadReservation reserveUpload(String sourceZoneKey, String contentType, long contentLength);

    UploadedObject verifyUploaded(String sourceZoneKey);

    record UploadReservation(String uploadUrl, Instant expiresAt) {
    }

    record UploadedObject(String contentSha256, String contentType, long contentLength) {
    }
}
