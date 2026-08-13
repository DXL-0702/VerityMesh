package com.veritymesh.platform.knowledge;

public final class SourceObjectNotFoundException extends RuntimeException {

    public SourceObjectNotFoundException() {
        super("uploaded source object was not found");
    }
}
