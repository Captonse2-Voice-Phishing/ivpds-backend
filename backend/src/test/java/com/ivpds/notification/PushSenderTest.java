package com.ivpds.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

/** The push channel when it is switched off, which is its default. */
class PushSenderTest {

    private static final StubPushServer expo = new StubPushServer();

    @AfterAll
    static void stopStub() {
        expo.close();
    }

    @Test
    void nothingIsLookedUpOrSentWhilePushIsSwitchedOff() throws Exception {
        PushDeviceRepository devices = mock(PushDeviceRepository.class);
        PushSender sender = new PushSender(new PushProperties(false, URI.create(expo.url()), "",
                Duration.ofSeconds(1), Duration.ofSeconds(1)), devices, new ObjectMapper());
        try {
            sender.onNotificationCreated(new NotificationCreatedEvent(UUID.randomUUID(), UUID.randomUUID(),
                    Notification.Type.HIGH_RISK_CALL, "Tiêu đề", "Nội dung", UUID.randomUUID(), UUID.randomUUID()));
            Thread.sleep(300);
        } finally {
            sender.shutdown();
        }

        verifyNoInteractions(devices);
        assertThat(expo.received()).isEmpty();
    }
}
