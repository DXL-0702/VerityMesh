package com.veritymesh.platform.knowledge;

public final class SourceRevisionNotFoundException extends RuntimeException {

    public SourceRevisionNotFoundException(String sourceRevisionId) {
        super("source revision not found: " + sourceRevisionId);
    }
}
