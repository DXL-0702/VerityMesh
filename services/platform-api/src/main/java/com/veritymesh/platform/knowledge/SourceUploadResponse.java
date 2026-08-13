package com.veritymesh.platform.knowledge;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record SourceUploadResponse(
        String sourceRevisionId,
        String sourceObjectId,
        String taskId,
        String uploadUrl,
        Instant uploadExpiresAt) {
}
