package com.veritymesh.platform.knowledge;

public final class SourceStorageNotConfigured extends RuntimeException {

    public SourceStorageNotConfigured() {
        super("source storage adapter is not configured");
    }
}
