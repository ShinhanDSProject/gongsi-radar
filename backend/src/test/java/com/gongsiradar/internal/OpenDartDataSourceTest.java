package com.gongsiradar.internal;

import com.gongsiradar.data.source.DataSourceException;
import com.gongsiradar.data.source.OpenDartDataSource;
import com.gongsiradar.data.client.SourceHttp;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OpenDART 소스의 캐시·오류 코드 규칙(네트워크 없이 가짜 HTTP로). 실제 키·응답으로는 검증하지 않았다.
 * 000은 캐시하고 013은 캐시하지 않으며(나중에 생길 수 있음), 020은 예외. 캐시 적중은 호출 수에 들지 않는다.
 */
class OpenDartDataSourceTest {

    static final Clock CLOCK = Clock.fixed(Instant.parse("2026-10-15T03:00:00Z"), ZoneId.of("Asia/Seoul"));

    static class FakeHttp implements SourceHttp {
        final List<String> urls = new ArrayList<>();
        String body;

        @Override
        public byte[] get(String url, Map<String, ?> params, Duration timeout) throws IOException {
            urls.add(url + "?" + SourceHttp.query(params));
            if (body == null) throw new IOException("connection refused");
            return body.getBytes(StandardCharsets.UTF_8);
        }
    }

    @Test
    void 정상_응답은_캐시하고_다시_부르지_않는다(@TempDir Path dir) {
        FakeHttp http = new FakeHttp();
        http.body = "{\"status\":\"000\",\"list\":[{\"rcept_no\":\"20260317000388\",\"account_nm\":\"매출액\",\"sj_div\":\"IS\"}]}";
        OpenDartDataSource src = new OpenDartDataSource("k", null, dir, null, http, CLOCK, Duration.ZERO);
        assertThat(src.financials("00999001", 2025, "11011").fsDiv()).isEqualTo("CFS");
        assertThat(src.financials("00999001", 2025, "11011").rows()).hasSize(1);
        assertThat(src.calls()).isEqualTo(1);
        assertThat(http.urls.get(0)).startsWith("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?crtfc_key=k")
                .contains("fs_div=CFS").contains("reprt_code=11011");
        assertThat(Files.exists(dir.resolve("opendart/fnltt_00999001_2025_11011_CFS.json"))).isTrue();
    }

    @Test
    void 데이터_없음_013은_캐시하지_않고_OFS까지_본_뒤_예외(@TempDir Path dir) {
        FakeHttp http = new FakeHttp();
        http.body = "{\"status\":\"013\",\"message\":\"조회된 데이타가 없습니다.\"}";
        OpenDartDataSource src = new OpenDartDataSource("k", null, dir, null, http, CLOCK, Duration.ZERO);
        assertThatThrownBy(() -> src.financials("00999001", 2025, "11011"))
                .isInstanceOf(DataSourceException.class).hasMessageContaining("013");
        assertThat(src.calls()).isEqualTo(2);   // CFS, OFS
        assertThat(dir.resolve("opendart/fnltt_00999001_2025_11011_CFS.json")).doesNotExist();
    }

    @Test
    void 한도_초과_020과_연결_실패는_예외(@TempDir Path dir) {
        FakeHttp http = new FakeHttp();
        http.body = "{\"status\":\"020\",\"message\":\"사용한도 초과\"}";
        OpenDartDataSource src = new OpenDartDataSource("k", null, dir, null, http, CLOCK, Duration.ZERO);
        assertThatThrownBy(() -> src.lawsuits("00999001", "20250101", "20251231")).hasMessageContaining("020");
        http.body = null;
        assertThatThrownBy(() -> src.governance("00999001", 2025, "11011")).hasMessageContaining("호출 실패");
        assertThat(http.urls).hasSize(1 + 3);   // 연결 실패는 세 번까지 시도
    }

    @Test
    void 시세_키가_없으면_빈_목록이고_호출하지_않는다(@TempDir Path dir) {
        FakeHttp http = new FakeHttp();
        OpenDartDataSource src = new OpenDartDataSource("k", "", dir, null, http, CLOCK, Duration.ZERO);
        assertThat(src.market("999001")).isEmpty();
        assertThat(src.marketHistory()).isEmpty();
        assertThat(src.indexSeries("코스피")).isEmpty();
        assertThat(http.urls).isEmpty();
    }

    @Test
    void 키가_없으면_시작하지_않는다(@TempDir Path dir) {
        assertThatThrownBy(() -> new OpenDartDataSource("", null, dir, null, new FakeHttp(), CLOCK, Duration.ZERO))
                .hasMessageContaining("OPENDART_API_KEY");
    }
}
