package com.veritymesh.platform.knowledge;

import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public final class KafkaProducerEventSink implements KafkaEventProducer, AutoCloseable {

    private final KafkaProducer<String, String> producer;
    private final Duration sendTimeout;

    public KafkaProducerEventSink(KafkaProducer<String, String> producer, Duration sendTimeout) {
        this.producer = producer;
        this.sendTimeout = sendTimeout;
    }

    @Override
    public void send(String topic, String key, String payload) {
        try {
            producer.send(new ProducerRecord<>(topic, key, payload))
                    .get(sendTimeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new OutboxPublishException("Kafka outbox publish was interrupted", error);
        } catch (ExecutionException | TimeoutException | RuntimeException error) {
            throw new OutboxPublishException("Kafka outbox publish failed", error);
        }
    }

    @Override
    public void close() {
        producer.close(Duration.ofSeconds(5));
    }
}
