package com.ivpds.audio;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ivpds.common.error.ApiException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class AudioFormatTest {

    @Test
    void recognisesEachSupportedFormatByExtensionAndLeadingBytes() {
        assertThat(AudioFormat.detect("a.mp3", ascii("ID3\u0004\u0000\u0000\u0000\u0000\u0000\u0000")))
                .isEqualTo(AudioFormat.MP3);
        assertThat(AudioFormat.detect("a.mp3", bytes(0xFF, 0xFB, 0x90, 0x64))).isEqualTo(AudioFormat.MP3);
        assertThat(AudioFormat.detect("a.wav", ascii("RIFF$\u0000\u0000\u0000WAVE")))
                .isEqualTo(AudioFormat.WAV);
        assertThat(AudioFormat.detect("a.m4a", ascii("\u0000\u0000\u0000 ftypM4A ")))
                .isEqualTo(AudioFormat.M4A);
        assertThat(AudioFormat.detect("a.3gp", ascii("\u0000\u0000\u0000\u0018ftyp3gp4")))
                .isEqualTo(AudioFormat.THREE_GP);
        assertThat(AudioFormat.detect("a.aac", bytes(0xFF, 0xF1, 0x50, 0x80))).isEqualTo(AudioFormat.AAC);
        assertThat(AudioFormat.detect("a.ogg", ascii("OggS\u0000\u0002"))).isEqualTo(AudioFormat.OGG);
        assertThat(AudioFormat.detect("a.webm", bytes(0x1A, 0x45, 0xDF, 0xA3))).isEqualTo(AudioFormat.WEBM);
        assertThat(AudioFormat.detect("a.amr", ascii("#!AMR\n"))).isEqualTo(AudioFormat.AMR);
        assertThat(AudioFormat.detect("a.flac", ascii("fLaC\u0000\u0000"))).isEqualTo(AudioFormat.FLAC);
    }

    @Test
    void extensionIsCaseInsensitiveAndUsesTheLastDot() {
        assertThat(AudioFormat.detect("Cuộc gọi.lúc.9h.WAV", ascii("RIFF$\u0000\u0000\u0000WAVE")))
                .isEqualTo(AudioFormat.WAV);
    }

    @Test
    void rejectsUnsupportedOrMissingExtension() {
        for (String name : new String[] {"notes.txt", "malware.exe", "noextension", "trailingdot.", null}) {
            assertThatThrownBy(() -> AudioFormat.detect(name, ascii("RIFF$\u0000\u0000\u0000WAVE")))
                    .isInstanceOf(ApiException.class)
                    .extracting(e -> ((ApiException) e).getCode()).isEqualTo("UNSUPPORTED_AUDIO_FORMAT");
        }
    }

    @Test
    void rejectsContentThatDoesNotMatchTheExtension() {
        byte[] text = ascii("This is not audio at all.");
        byte[] wav = ascii("RIFF$\u0000\u0000\u0000WAVE");
        byte[] windowsExecutable = ascii("MZ\u0090\u0000\u0003\u0000\u0000\u0000");

        for (String name : new String[] {"a.mp3", "a.wav", "a.m4a", "a.aac", "a.ogg", "a.webm", "a.3gp", "a.amr",
                "a.flac"}) {
            assertInvalidContent(name, text);
            assertInvalidContent(name, windowsExecutable);
            assertInvalidContent(name, new byte[0]);
        }
        assertInvalidContent("a.mp3", wav);
        // RIFF container that is not WAVE (an AVI video).
        assertInvalidContent("a.wav", ascii("RIFF$\u0000\u0000\u0000AVI "));
        // Truncated header.
        assertInvalidContent("a.wav", ascii("RIFF"));
    }

    private static void assertInvalidContent(String filename, byte[] header) {
        assertThatThrownBy(() -> AudioFormat.detect(filename, header))
                .as("%s with %d header bytes", filename, header.length)
                .isInstanceOf(ApiException.class)
                .extracting(e -> ((ApiException) e).getCode()).isEqualTo("INVALID_AUDIO_CONTENT");
    }

    private static byte[] ascii(String s) {
        return s.getBytes(StandardCharsets.ISO_8859_1);
    }

    private static byte[] bytes(int... values) {
        byte[] result = new byte[values.length];
        for (int i = 0; i < values.length; i++) {
            result[i] = (byte) values[i];
        }
        return result;
    }
}
