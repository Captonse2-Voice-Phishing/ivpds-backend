package com.ivpds.common;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;

class PhoneNumbersTest {

    @ParameterizedTest
    @CsvSource({
            "0901234567,        +84901234567",
            "090 123 4567,      +84901234567",
            "090.123.4567,      +84901234567",
            "(090) 123-4567,    +84901234567",
            "84901234567,       +84901234567",
            "+84901234567,      +84901234567",
            "+84 901 234 567,   +84901234567",
            "02812345678,       +842812345678",
            "+12025550123,      +12025550123",
            "19001234,          19001234",
            "113113,            113113",
    })
    void normalizesToOneCanonicalForm(String raw, String expected) {
        assertThat(PhoneNumbers.normalize(raw)).isEqualTo(expected);
    }

    @ParameterizedTest
    @NullSource
    @ValueSource(strings = {"", "   "})
    void blankMeansNoNumber(String raw) {
        assertThat(PhoneNumbers.normalize(raw)).isNull();
    }

    @ParameterizedTest
    @ValueSource(strings = {"abc", "12345", "09012345678901234", "090-12a-4567", "++84901234567", "0901234567+"})
    void rejectsThingsThatAreNotPhoneNumbers(String raw) {
        assertThatThrownBy(() -> PhoneNumbers.normalize(raw)).isInstanceOf(IllegalArgumentException.class);
    }
}
