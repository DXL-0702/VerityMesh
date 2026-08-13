package com.veritymesh.platform.knowledge;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@Configuration
@EnableConfigurationProperties(SourceStorageProperties.class)
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
}
