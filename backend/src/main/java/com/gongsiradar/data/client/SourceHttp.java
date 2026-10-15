package com.gongsiradar.data.client;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.StringJoiner;

/**
 * 원천 API GET. 테스트에서 가짜 응답으로 바꿀 수 있게 인터페이스로 둔다.
 * <p>
 * 쿼리 값은 UTF-8로 인코딩한다. 공공데이터포털 serviceKey는 '디코딩' 키를 넣는다(여기서 인코딩한다 —
 * 인코딩 키를 넣으면 두 번 인코딩돼 SERVICE_KEY_IS_NOT_REGISTERED가 난다).
 */
public interface SourceHttp {

    /** 2xx면 본문 바이트, 아니면 {@link IOException}. */
    byte[] get(String url, Map<String, ?> params, Duration timeout) throws IOException;

    static String query(Map<String, ?> params) {
        StringJoiner j = new StringJoiner("&");
        params.forEach((k, v) -> j.add(URLEncoder.encode(k, StandardCharsets.UTF_8) + "="
                + URLEncoder.encode(String.valueOf(v), StandardCharsets.UTF_8)));
        return j.toString();
    }

    /** JDK HttpClient 구현. 리다이렉트는 따라간다. */
    static SourceHttp jdk() {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
        return (url, params, timeout) -> {
            String q = query(params);
            HttpRequest req = HttpRequest.newBuilder(URI.create(q.isEmpty() ? url : url + "?" + q))
                    .timeout(timeout).GET().build();
            try {
                HttpResponse<byte[]> res = client.send(req, HttpResponse.BodyHandlers.ofByteArray());
                if (res.statusCode() / 100 != 2) {
                    throw new IOException("HTTP " + res.statusCode());
                }
                return res.body();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IOException("요청이 중단됐습니다", e);
            }
        };
    }
}
