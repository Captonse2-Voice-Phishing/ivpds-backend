package com.ivpds.call;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ivpds.audio.AudioFileRepository;
import com.ivpds.audio.AudioStorage;
import com.ivpds.common.error.ApiException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;

/**
 * Failure paths that cannot be provoked against real infrastructure: what happens to an uploaded
 * object when the database step fails afterwards. The happy path is covered end to end in
 * UserCallAudioIntegrationTest.
 */
class CallServiceTest {

    private static final byte[] WAV = "RIFF$\u0000\u0000\u0000WAVEfmt ".getBytes(StandardCharsets.ISO_8859_1);

    private CallRecordRepository calls;
    private AudioFileRepository audioFiles;
    private AudioStorage storage;
    private PlatformTransactionManager transactionManager;
    private CallService service;

    @BeforeEach
    void setUp() {
        calls = mock(CallRecordRepository.class);
        audioFiles = mock(AudioFileRepository.class);
        storage = mock(AudioStorage.class);
        transactionManager = mock(PlatformTransactionManager.class);
        when(transactionManager.getTransaction(any())).thenReturn(mock(TransactionStatus.class));
        when(storage.bucket()).thenReturn("ivpds-audio");
        service = new CallService(calls, audioFiles, storage, transactionManager);
    }

    @Test
    void uploadedObjectIsRemovedAndTransactionRolledBackWhenSavingMetadataFails() {
        when(calls.save(any())).thenThrow(new DataIntegrityViolationException("database is unhappy"));
        MockMultipartFile file = new MockMultipartFile("audio", "call.wav", "audio/wav", WAV);

        assertThatThrownBy(() -> service.create(UUID.randomUUID(), file, null, null, CallSource.UPLOADED))
                .isInstanceOf(DataIntegrityViolationException.class);

        ArgumentCaptor<String> uploadedKey = ArgumentCaptor.forClass(String.class);
        verify(storage).put(uploadedKey.capture(), any(), eq((long) WAV.length), eq("audio/wav"));
        verify(storage).deleteQuietly(uploadedKey.getValue());
        verify(transactionManager).rollback(any());
        verify(transactionManager, never()).commit(any());
    }

    @Test
    void nothingIsUploadedWhenTheFileIsRejected() {
        MockMultipartFile notAudio = new MockMultipartFile("audio", "call.wav", "audio/wav",
                "plain text pretending to be audio".getBytes(StandardCharsets.UTF_8));
        MockMultipartFile empty = new MockMultipartFile("audio", "call.wav", "audio/wav", new byte[0]);
        MockMultipartFile valid = new MockMultipartFile("audio", "call.wav", "audio/wav", WAV);

        assertThatThrownBy(() -> service.create(UUID.randomUUID(), notAudio, null, null, CallSource.UPLOADED))
                .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.create(UUID.randomUUID(), empty, null, null, CallSource.UPLOADED))
                .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.create(UUID.randomUUID(), valid, "not a number", null, CallSource.UPLOADED))
                .isInstanceOf(ApiException.class);

        verify(storage, never()).put(anyString(), any(), anyLong(), anyString());
        verify(calls, never()).save(any());
    }
}
