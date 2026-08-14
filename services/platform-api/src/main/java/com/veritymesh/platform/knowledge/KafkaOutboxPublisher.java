package com.veritymesh.platform.knowledge;

import java.time.Clock;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.transaction.annotation.Transactional;

public final class KafkaOutboxPublisher {

    private static final String SOURCE_REVISION_SUBMITTED = "SourceRevisionSubmitted";

    private final OutboxEventRepository outboxEventRepository;
    private final KafkaEventProducer kafkaEventProducer;
    private final KafkaOutboxProperties properties;
    private final Clock clock;

    public KafkaOutboxPublisher(
            OutboxEventRepository outboxEventRepository,
            KafkaEventProducer kafkaEventProducer,
            KafkaOutboxProperties properties,
            Clock clock) {
        this.outboxEventRepository = outboxEventRepository;
        this.kafkaEventProducer = kafkaEventProducer;
        this.properties = properties;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${veritymesh.outbox.publisher.poll-interval-ms:1000}")
    @Transactional
    public int publishPending() {
        List<OutboxEventEntity> events = outboxEventRepository
                .findByPublishedAtIsNullOrderByOccurredAtAsc(PageRequest.of(0, properties.getBatchSize()));
        int published = 0;
        for (OutboxEventEntity event : events) {
            kafkaEventProducer.send(topicFor(event), event.getAggregateId(), event.getPayload());
            event.markPublished(clock.instant());
            outboxEventRepository.save(event);
            published++;
        }
        return published;
    }

    private String topicFor(OutboxEventEntity event) {
        if (SOURCE_REVISION_SUBMITTED.equals(event.getEventType())) {
            return properties.getSourceRevisionTopic();
        }
        throw new IllegalArgumentException("unsupported outbox event type: " + event.getEventType());
    }
}
