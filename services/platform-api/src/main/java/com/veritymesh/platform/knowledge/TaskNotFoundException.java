package com.veritymesh.platform.knowledge;

public final class TaskNotFoundException extends RuntimeException {

    public TaskNotFoundException(String taskId) {
        super("task not found: " + taskId);
    }
}
