package com.gongsiradar.common.util;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class KsicTest {

    @Test
    void 업종_코드를_중분류_이름으로_바꾸고_표에_없으면_대분류_이름을_쓴다() {
        assertThat(Ksic.name("264")).isEqualTo("전자부품·컴퓨터·영상·음향·통신장비 제조업");
        assertThat(Ksic.name("64992")).isEqualTo("금융업");
        assertThat(Ksic.name("06")).isEqualTo("광업");            // 중분류 표에 없음 → 대분류
        assertThat(Ksic.name(null)).isNull();
        assertThat(Ksic.name("")).isNull();
        assertThat(Ksic.name("xx")).isNull();
    }
}
