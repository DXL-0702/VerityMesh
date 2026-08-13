package com.veritymesh.platform.knowledge;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record SourceUploadRequest(
        @NotBlank @Size(max = 512) String filename,
        @NotBlank @Size(max = 256) String contentType,
        @Min(0) long contentLength,
        @NotBlank @Pattern(regexp = "[0-9a-f]{64}") String contentSha256) {
}
