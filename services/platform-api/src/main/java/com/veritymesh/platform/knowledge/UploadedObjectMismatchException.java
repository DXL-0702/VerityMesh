package com.veritymesh.platform.knowledge;

public final class UploadedObjectMismatchException extends RuntimeException {

    public UploadedObjectMismatchException(String sourceRevisionId) {
        super("uploaded object does not match the reserved source revision: " + sourceRevisionId);
    }
}
