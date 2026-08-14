package com.veritymesh.platform.knowledge;

@FunctionalInterface
public interface KafkaEventProducer {

    void send(String topic, String key, String payload);
}
