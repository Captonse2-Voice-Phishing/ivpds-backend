package com.ivpds;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistrar;

/** Starts Mailpit and points Spring Mail at it. */
@TestConfiguration(proxyBeanMethods = false)
public class MailpitConfig {

    @Bean
    MailpitContainer mailpit() {
        return new MailpitContainer();
    }

    @Bean
    DynamicPropertyRegistrar mailProperties(MailpitContainer mailpit) {
        return registry -> {
            registry.add("spring.mail.host", mailpit::getHost);
            registry.add("spring.mail.port", mailpit::smtpPort);
        };
    }
}
