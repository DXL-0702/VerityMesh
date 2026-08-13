package com.veritymesh.platform.knowledge;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class KnowledgeConfiguration {

    @Bean
    Clock platformClock() {
        return Clock.systemUTC();
    }

    @Bean
    SourceStorage sourceStorage() {
        return new UnavailableSourceStorage();
    }
}
