package com.veritymesh.platform.knowledge;

import java.time.Clock;
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@Configuration
@EnableScheduling
@EnableConfigurationProperties({SourceStorageProperties.class, KafkaOutboxProperties.class})
public class KnowledgeConfiguration {

    @Bean
    Clock platformClock() {
        return Clock.systemUTC();
    }

    @Bean(destroyMethod = "close")
    SourceStorage sourceStorage(SourceStorageProperties properties) {
        if (!properties.isEnabled()) {
            return new UnavailableSourceStorage();
        }
        return new S3SourceStorage(properties);
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(prefix = "veritymesh.outbox.publisher", name = "enabled", havingValue = "true")
    KafkaProducerEventSink kafkaEventProducer(KafkaOutboxProperties properties) {
        properties.validate();
        Properties producerProperties = new Properties();
        producerProperties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, properties.getBootstrapServers());
        producerProperties.put(ProducerConfig.CLIENT_ID_CONFIG, "veritymesh-platform-api");
        producerProperties.put(ProducerConfig.ACKS_CONFIG, "all");
        producerProperties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
        producerProperties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        producerProperties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        return new KafkaProducerEventSink(
                new KafkaProducer<String, String>(producerProperties), properties.getSendTimeout());
    }

    @Bean
    @ConditionalOnProperty(prefix = "veritymesh.outbox.publisher", name = "enabled", havingValue = "true")
    KafkaOutboxPublisher kafkaOutboxPublisher(
            OutboxEventRepository outboxEventRepository,
            KafkaEventProducer kafkaEventProducer,
            KafkaOutboxProperties properties,
            Clock clock) {
        return new KafkaOutboxPublisher(outboxEventRepository, kafkaEventProducer, properties, clock);
    }
}
