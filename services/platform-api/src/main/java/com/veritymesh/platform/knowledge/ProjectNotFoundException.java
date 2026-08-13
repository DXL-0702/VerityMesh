package com.veritymesh.platform.knowledge;

public final class ProjectNotFoundException extends RuntimeException {

    public ProjectNotFoundException(String projectId) {
        super("project not found: " + projectId);
    }
}
