package com.veritymesh.platform.knowledge;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class KnowledgeErrorHandler {

    @ExceptionHandler(ProjectNotFoundException.class)
    ResponseEntity<Map<String, Object>> projectNotFound(
            ProjectNotFoundException error, HttpServletRequest request) {
        return error(HttpStatus.NOT_FOUND, "project_not_found", error.getMessage(), false, request);
    }

    @ExceptionHandler(TaskNotFoundException.class)
    ResponseEntity<Map<String, Object>> taskNotFound(
            TaskNotFoundException error, HttpServletRequest request) {
        return error(HttpStatus.NOT_FOUND, "task_not_found", error.getMessage(), false, request);
    }

    @ExceptionHandler(SourceRevisionNotFoundException.class)
    ResponseEntity<Map<String, Object>> sourceRevisionNotFound(
            SourceRevisionNotFoundException error, HttpServletRequest request) {
        return error(HttpStatus.NOT_FOUND, "source_revision_not_found", error.getMessage(), false, request);
    }

    @ExceptionHandler(IdempotencyConflictException.class)
    ResponseEntity<Map<String, Object>> idempotencyConflict(
            IdempotencyConflictException error, HttpServletRequest request) {
        return error(HttpStatus.CONFLICT, "idempotency_conflict", error.getMessage(), false, request);
    }

    @ExceptionHandler(UploadedObjectMismatchException.class)
    ResponseEntity<Map<String, Object>> uploadedObjectMismatch(
            UploadedObjectMismatchException error, HttpServletRequest request) {
        return error(HttpStatus.UNPROCESSABLE_ENTITY, "uploaded_object_mismatch", error.getMessage(), false, request);
    }

    @ExceptionHandler(SourceObjectNotFoundException.class)
    ResponseEntity<Map<String, Object>> sourceObjectNotFound(
            SourceObjectNotFoundException error, HttpServletRequest request) {
        return error(HttpStatus.UNPROCESSABLE_ENTITY, "uploaded_object_missing", error.getMessage(), false, request);
    }

    @ExceptionHandler(SourceStorageAccessException.class)
    ResponseEntity<Map<String, Object>> sourceStorageAccess(
            SourceStorageAccessException error, HttpServletRequest request) {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "source_storage_unavailable", error.getMessage(), true, request);
    }

    @ExceptionHandler(SourceStorageNotConfigured.class)
    ResponseEntity<Map<String, Object>> sourceStorageUnavailable(
            SourceStorageNotConfigured error, HttpServletRequest request) {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "source_storage_unavailable", error.getMessage(), true, request);
    }

    private ResponseEntity<Map<String, Object>> error(
            HttpStatus status,
            String code,
            String message,
            boolean retryable,
            HttpServletRequest request) {
        String requestId = request.getHeader("X-Request-Id");
        if (requestId == null || requestId.isBlank()) {
            requestId = "unavailable";
        }
        return ResponseEntity.status(status).body(Map.of(
                "error", Map.of(
                        "code", code,
                        "message", message,
                        "request_id", requestId,
                        "retryable", retryable)));
    }
}
