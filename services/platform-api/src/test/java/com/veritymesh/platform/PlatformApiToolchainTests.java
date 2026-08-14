package com.veritymesh.platform;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.LoggerContext;
import java.io.IOException;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.support.PropertiesLoaderUtils;
import org.springframework.util.ClassUtils;

class PlatformApiToolchainTests {

    private static final ClassLoader CLASS_LOADER = PlatformApiToolchainTests.class.getClassLoader();

    @Test
    void selectsServletApplicationRuntime() {
        SpringApplication application = new SpringApplication(PlatformApiApplication.class);

        assertThat(application.getWebApplicationType()).isEqualTo(WebApplicationType.SERVLET);
    }

    @Test
    void keepsMigrationsOutOfTheApplicationRuntime() throws IOException {
        Properties properties = PropertiesLoaderUtils.loadProperties(
                new ClassPathResource("application.properties"));

        assertThat(properties)
                .containsEntry("spring.main.web-application-type", "servlet")
                .containsEntry("spring.jpa.open-in-view", "false")
                .containsEntry("spring.flyway.enabled", "false");
    }

    @Test
    void usesTheSelectedSecurityAndLoggingStacks() {
        assertThat(ClassUtils.isPresent(
                        "org.springframework.security.oauth2.jwt.JwtDecoder", CLASS_LOADER))
                .isTrue();
        assertThat(ClassUtils.isPresent(
                        "software.amazon.awssdk.services.s3.S3Client", CLASS_LOADER))
                .isTrue();
        assertThat(LoggerFactory.getILoggerFactory()).isInstanceOf(LoggerContext.class);
    }

    @Test
    void leavesRejectedLibrariesOffTheClasspath() {
        assertThat(ClassUtils.isPresent("io.jsonwebtoken.Jwts", CLASS_LOADER)).isFalse();
        assertThat(ClassUtils.isPresent(
                        "com.github.xiaoymin.knife4j.spring.configuration.Knife4jAutoConfiguration",
                        CLASS_LOADER))
                .isFalse();
    }
}
