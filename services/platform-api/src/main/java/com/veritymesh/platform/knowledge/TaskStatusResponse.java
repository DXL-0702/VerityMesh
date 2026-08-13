package com.veritymesh.platform.knowledge;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record TaskStatusResponse(
        String taskId,
        String sourceRevisionId,
        SourceRevisionStatus status,
        int progress,
        String failureCode,
        Instant updatedAt) {
}
