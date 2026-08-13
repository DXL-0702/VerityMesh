package com.veritymesh.platform.knowledge;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SourceRevisionService {

    private final ProjectRepository projectRepository;
    private final SourceObjectRepository sourceObjectRepository;
    private final SourceRevisionRepository sourceRevisionRepository;
    private final ProcessingTaskRepository processingTaskRepository;
    private final OutboxEventRepository outboxEventRepository;
    private final SourceStorage sourceStorage;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public SourceRevisionService(
            ProjectRepository projectRepository,
            SourceObjectRepository sourceObjectRepository,
            SourceRevisionRepository sourceRevisionRepository,
            ProcessingTaskRepository processingTaskRepository,
            OutboxEventRepository outboxEventRepository,
            SourceStorage sourceStorage,
            ObjectMapper objectMapper,
            Clock clock) {
        this.projectRepository = projectRepository;
        this.sourceObjectRepository = sourceObjectRepository;
        this.sourceRevisionRepository = sourceRevisionRepository;
        this.processingTaskRepository = processingTaskRepository;
        this.outboxEventRepository = outboxEventRepository;
        this.sourceStorage = sourceStorage;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public SourceUploadResponse createUpload(
            String projectId,
            String idempotencyKey,
            String traceId,
            String requestId,
            SourceUploadRequest request) {
        if (!projectRepository.existsById(projectId)) {
            throw new ProjectNotFoundException(projectId);
        }

        SourceRevisionEntity existing = sourceRevisionRepository
                .findByProjectIdAndIdempotencyKey(projectId, idempotencyKey)
                .orElse(null);
        if (existing != null) {
            if (!sameRequest(existing, request)) {
                throw new IdempotencyConflictException(idempotencyKey);
            }
            SourceStorage.UploadReservation reservation = sourceStorage.reserveUpload(
                    existing.getSourceZoneKey(), existing.getContentType(), existing.getContentLength());
            ProcessingTaskEntity task = processingTaskRepository.findById("task-" + existing.getId())
                    .orElseThrow(() -> new IllegalStateException("source revision task is missing"));
            return response(existing, task, reservation);
        }

        Instant now = clock.instant();
        String sourceObjectId = "source-object-" + UUID.randomUUID();
        String sourceRevisionId = "source-revision-" + UUID.randomUUID();
        String taskId = "task-" + sourceRevisionId;
        String sourceZoneKey = "source-zone/" + projectId + "/" + sourceRevisionId;
        SourceStorage.UploadReservation reservation = sourceStorage.reserveUpload(
                sourceZoneKey, request.contentType(), request.contentLength());

        SourceObjectEntity sourceObject = new SourceObjectEntity(sourceObjectId, projectId, "UPLOAD", now);
        sourceObjectRepository.save(sourceObject);
        SourceRevisionEntity revision = new SourceRevisionEntity(
                sourceRevisionId,
                projectId,
                sourceObjectId,
                1,
                request.filename(),
                sourceZoneKey,
                request.contentSha256(),
                request.contentType(),
                request.contentLength(),
                idempotencyKey,
                SourceRevisionStatus.PENDING_UPLOAD,
                now);
        ProcessingTaskEntity task = new ProcessingTaskEntity(
                taskId, sourceRevisionId, SourceRevisionStatus.PENDING_UPLOAD, 0, 0, now);
        sourceRevisionRepository.save(revision);
        processingTaskRepository.save(task);
        return response(revision, task, reservation);
    }

    @Transactional
    public TaskStatusResponse completeUpload(String sourceRevisionId, String traceId, String requestId) {
        SourceRevisionEntity revision = sourceRevisionRepository.findById(sourceRevisionId)
                .orElseThrow(() -> new SourceRevisionNotFoundException(sourceRevisionId));
        ProcessingTaskEntity task = processingTaskRepository.findById("task-" + sourceRevisionId)
                .orElseThrow(() -> new IllegalStateException("source revision task is missing"));
        if (revision.getStatus() != SourceRevisionStatus.PENDING_UPLOAD) {
            return toTaskStatus(task);
        }

        SourceStorage.UploadedObject uploaded = sourceStorage.verifyUploaded(revision.getSourceZoneKey());
        if (!revision.getContentSha256().equals(uploaded.contentSha256())
                || !revision.getContentType().equals(uploaded.contentType())
                || revision.getContentLength() != uploaded.contentLength()) {
            throw new UploadedObjectMismatchException(sourceRevisionId);
        }

        Instant now = clock.instant();
        revision.markQueued();
        task.markQueued(now);
        outboxEventRepository.save(new OutboxEventEntity(
                "evt-" + sourceRevisionId,
                "SourceRevision",
                sourceRevisionId,
                "SourceRevisionSubmitted",
                "1.0",
                "source-revision-submitted-" + sourceRevisionId,
                eventPayload(
                        "evt-" + sourceRevisionId,
                        revision.getProjectId(),
                        revision.getSourceObjectId(),
                        sourceRevisionId,
                        revision.getSourceZoneKey(),
                        revision.getContentSha256(),
                        revision.getContentType(),
                        revision.getContentLength(),
                        traceId,
                        requestId,
                        revision.getIdempotencyKey(),
                        now,
                        now.plus(Duration.ofMinutes(5))),
                now));
        return toTaskStatus(task);
    }

    @Transactional(readOnly = true)
    public TaskStatusResponse getTask(String taskId) {
        ProcessingTaskEntity task = processingTaskRepository.findById(taskId)
                .orElseThrow(() -> new TaskNotFoundException(taskId));
        return toTaskStatus(task);
    }

    private SourceUploadResponse response(
            SourceRevisionEntity revision,
            ProcessingTaskEntity task,
            SourceStorage.UploadReservation reservation) {
        return new SourceUploadResponse(
                revision.getId(),
                revision.getSourceObjectId(),
                task.getId(),
                reservation.uploadUrl(),
                reservation.expiresAt());
    }

    private String eventPayload(
            String eventId,
            String projectId,
            String sourceObjectId,
            String sourceRevisionId,
            String sourceZoneKey,
            String contentSha256,
            String contentType,
            long contentLength,
            String traceId,
            String requestId,
            String idempotencyKey,
            Instant occurredAt,
            Instant deadlineAt) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema_version", "1.0");
        payload.put("event_id", eventId);
        payload.put("event_type", "SourceRevisionSubmitted");
        payload.put("occurred_at", occurredAt.toString());
        payload.put("trace_id", traceId);
        payload.put("request_id", requestId);
        payload.put("idempotency_key", idempotencyKey);
        payload.put("project_id", projectId);
        payload.put("source_object_id", sourceObjectId);
        payload.put("source_revision_id", sourceRevisionId);
        payload.put("source_zone_key", sourceZoneKey);
        payload.put("content_sha256", contentSha256);
        payload.put("content_type", contentType);
        payload.put("content_length", contentLength);
        payload.put("deadline_at", deadlineAt.toString());
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException error) {
            throw new IllegalStateException("source revision event cannot be serialized", error);
        }
    }

    private boolean sameRequest(SourceRevisionEntity existing, SourceUploadRequest request) {
        return existing.getFilename().equals(request.filename())
                && existing.getContentType().equals(request.contentType())
                && existing.getContentLength() == request.contentLength()
                && existing.getContentSha256().equals(request.contentSha256());
    }

    private TaskStatusResponse toTaskStatus(ProcessingTaskEntity task) {
        return new TaskStatusResponse(
                task.getId(),
                task.getSourceRevisionId(),
                task.getStatus(),
                task.getProgress(),
                task.getFailureCode(),
                task.getUpdatedAt());
    }
}
