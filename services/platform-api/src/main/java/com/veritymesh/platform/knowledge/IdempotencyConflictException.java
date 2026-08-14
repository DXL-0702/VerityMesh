package com.veritymesh.platform.knowledge;

public final class IdempotencyConflictException extends RuntimeException {

    public IdempotencyConflictException(String idempotencyKey) {
        super("idempotency key conflicts with an existing source revision: " + idempotencyKey);
    }
}
