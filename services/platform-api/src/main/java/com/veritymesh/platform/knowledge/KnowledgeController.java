package com.veritymesh.platform.knowledge;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/v1")
public class KnowledgeController {

    private final SourceRevisionService sourceRevisionService;

    public KnowledgeController(SourceRevisionService sourceRevisionService) {
        this.sourceRevisionService = sourceRevisionService;
    }

    @PostMapping("/projects/{projectId}/source-revisions")
    @ResponseStatus(HttpStatus.CREATED)
    public SourceUploadResponse createUpload(
            @PathVariable @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String projectId,
            @RequestHeader("Idempotency-Key")
            @NotBlank @Size(min = 16, max = 256) @Pattern(regexp = "^\\S+$") String idempotencyKey,
            @RequestHeader("X-Trace-Id")
            @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String traceId,
            @RequestHeader("X-Request-Id")
            @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String requestId,
            @Valid @RequestBody SourceUploadRequest request) {
        return sourceRevisionService.createUpload(projectId, idempotencyKey, traceId, requestId, request);
    }

    @GetMapping("/tasks/{taskId}")
    public TaskStatusResponse getTask(
            @PathVariable @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String taskId,
            @RequestHeader("X-Trace-Id")
            @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String traceId,
            @RequestHeader("X-Request-Id")
            @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String requestId) {
        return sourceRevisionService.getTask(taskId);
    }

    @PostMapping("/source-revisions/{sourceRevisionId}/complete")
    public TaskStatusResponse completeUpload(
            @PathVariable @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String sourceRevisionId,
            @RequestHeader("X-Trace-Id")
            @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String traceId,
            @RequestHeader("X-Request-Id")
            @NotBlank @Size(max = 256) @Pattern(regexp = "^\\S+$") String requestId) {
        return sourceRevisionService.completeUpload(sourceRevisionId, traceId, requestId);
    }
}
