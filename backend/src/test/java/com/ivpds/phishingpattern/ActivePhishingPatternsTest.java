package com.ivpds.phishingpattern;

import static org.assertj.core.api.Assertions.assertThat;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

/** Which administrator patterns the rule engine of the AI service can use. */
class ActivePhishingPatternsTest {

    @Test
    void aPatternNeedsAKnownIndicatorAndAPhraseOfAtLeastTwoWords() {
        assertThat(ActivePhishingPatterns.usable("OTP_REQUEST", "đọc mã otp cho em")).isTrue();
        assertThat(ActivePhishingPatterns.usable("FINANCIAL_BAIT", "trúng thưởng")).isTrue();
        assertThat(ActivePhishingPatterns.usable("CALL_HANDOFF", "Chuyển máy, cho cán bộ!")).isTrue();
        // Counted exactly as the rule engine counts: runs of letters and digits in the phrase as typed.
        assertThat(ActivePhishingPatterns.usable("FINANCIAL_BAIT", "phây búc")).isTrue();
        assertThat(ActivePhishingPatterns.usable("URGENCY", "abc|xyz")).isTrue();
        assertThat(ActivePhishingPatterns.usable("URGENCY", "gấp | |")).isFalse();

        assertThat(ActivePhishingPatterns.usable("OTP_REQUEST", "otp")).isFalse();
        // Punctuation is not a word.
        assertThat(ActivePhishingPatterns.usable("OTP_REQUEST", "otp ?!")).isFalse();
        assertThat(ActivePhishingPatterns.usable("OTP_REQUEST", "   ")).isFalse();
        assertThat(ActivePhishingPatterns.usable("OTP_REQUEST", null)).isFalse();
        assertThat(ActivePhishingPatterns.usable("OTP_REQUEST", "a b ".repeat(60))).isFalse();
        assertThat(ActivePhishingPatterns.usable("MADE_UP_CODE", "đọc mã otp")).isFalse();
        // This indicator comes from how many people speak, not from words.
        assertThat(ActivePhishingPatterns.usable("COORDINATED_CALLERS", "đọc mã otp")).isFalse();
        assertThat(ActivePhishingPatterns.usable(null, "đọc mã otp")).isFalse();
    }

    @Test
    void toneMarksTypedAsSeparateCharactersDoNotSplitAWord() {
        String decomposed = Normalizer.normalize("tiền", Normalizer.Form.NFD);

        assertThat(decomposed).hasSizeGreaterThan(4);
        assertThat(ActivePhishingPatterns.wordCount(decomposed)).isEqualTo(1);
        assertThat(ActivePhishingPatterns.usable("MONEY_TRANSFER", decomposed)).isFalse();
        assertThat(ActivePhishingPatterns.usable("MONEY_TRANSFER", "chuyển " + decomposed)).isTrue();
    }
}
