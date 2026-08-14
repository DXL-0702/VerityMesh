package com.veritymesh.platform.knowledge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.domain.Pageable;

class KafkaOutboxPublisherTest {

    private static final Instant NOW = Instant.parse("2026-08-14T04:00:00Z");

    @Test
    void publishesSourceRevisionAndMarksItOnlyAfterKafkaAcceptsIt() {
        OutboxEventRepository repository = mock(OutboxEventRepository.class);
        KafkaEventProducer producer = mock(KafkaEventProducer.class);
        KafkaOutboxProperties properties = properties();
        OutboxEventEntity event = event("SourceRevisionSubmitted");
        when(repository.findByPublishedAtIsNullOrderByOccurredAtAsc(any(Pageable.class)))
                .thenReturn(List.of(event));

        KafkaOutboxPublisher publisher = new KafkaOutboxPublisher(
                repository, producer, properties, Clock.fixed(NOW, ZoneOffset.UTC));

        assertThat(publisher.publishPending()).isOne();
        verify(producer).send(
                "veritymesh.source-revision-submitted", "source-revision-1", "{\"event\":\"payload\"}");
        verify(repository).save(event);
        assertThat(event.getPublishedAt()).isEqualTo(NOW);
    }

    @Test
    void leavesEventUnpublishedWhenKafkaFails() {
        OutboxEventRepository repository = mock(OutboxEventRepository.class);
        KafkaEventProducer producer = mock(KafkaEventProducer.class);
        OutboxEventEntity event = event("SourceRevisionSubmitted");
        when(repository.findByPublishedAtIsNullOrderByOccurredAtAsc(any(Pageable.class)))
                .thenReturn(List.of(event));
        doThrow(new OutboxPublishException("broker unavailable", new IllegalStateException()))
                .when(producer)
                .send(any(), any(), any());

        KafkaOutboxPublisher publisher = new KafkaOutboxPublisher(
                repository, producer, properties(), Clock.fixed(NOW, ZoneOffset.UTC));

        assertThatThrownBy(publisher::publishPending)
                .isInstanceOf(OutboxPublishException.class)
                .hasMessage("broker unavailable");
        verify(repository, never()).save(any());
        assertThat(event.getPublishedAt()).isNull();
    }

    @Test
    void rejectsUnknownEventTypesWithoutMarkingThemPublished() {
        OutboxEventRepository repository = mock(OutboxEventRepository.class);
        KafkaEventProducer producer = mock(KafkaEventProducer.class);
        OutboxEventEntity event = event("UnknownEvent");
        when(repository.findByPublishedAtIsNullOrderByOccurredAtAsc(any(Pageable.class)))
                .thenReturn(List.of(event));

        KafkaOutboxPublisher publisher = new KafkaOutboxPublisher(
                repository, producer, properties(), Clock.fixed(NOW, ZoneOffset.UTC));

        assertThatThrownBy(publisher::publishPending)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("unsupported outbox event type: UnknownEvent");
        verify(producer, never()).send(any(), any(), any());
        verify(repository, never()).save(any());
    }

    @Test
    void appliesConfiguredBatchSizeWhenReadingPendingEvents() {
        OutboxEventRepository repository = mock(OutboxEventRepository.class);
        KafkaEventProducer producer = mock(KafkaEventProducer.class);
        KafkaOutboxProperties properties = properties();
        properties.setBatchSize(17);
        when(repository.findByPublishedAtIsNullOrderByOccurredAtAsc(any(Pageable.class)))
                .thenReturn(List.of());

        KafkaOutboxPublisher publisher = new KafkaOutboxPublisher(
                repository, producer, properties, Clock.fixed(NOW, ZoneOffset.UTC));

        assertThat(publisher.publishPending()).isZero();
        ArgumentCaptor<Pageable> pageable = ArgumentCaptor.forClass(Pageable.class);
        verify(repository).findByPublishedAtIsNullOrderByOccurredAtAsc(pageable.capture());
        assertThat(pageable.getValue().getPageNumber()).isZero();
        assertThat(pageable.getValue().getPageSize()).isEqualTo(17);
    }

    @Test
    void validatesEnabledPublisherSettings() {
        KafkaOutboxProperties properties = properties();
        properties.setBootstrapServers("");

        assertThatThrownBy(properties::validate)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("bootstrapServers");
    }

    private static KafkaOutboxProperties properties() {
        KafkaOutboxProperties properties = new KafkaOutboxProperties();
        properties.setBootstrapServers("localhost:19092");
        properties.setSourceRevisionTopic("veritymesh.source-revision-submitted");
        properties.setBatchSize(100);
        properties.setPollIntervalMs(1_000);
        return properties;
    }

    private static OutboxEventEntity event(String eventType) {
        return new OutboxEventEntity(
                "evt-source-revision-1",
                "SourceRevision",
                "source-revision-1",
                eventType,
                "1.0",
                "source-revision-submitted-source-revision-1",
                "{\"event\":\"payload\"}",
                Instant.parse("2026-08-14T03:59:00Z"));
    }
}
