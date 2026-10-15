package com.gongsiradar.internal;

import com.gongsiradar.data.Dart;
import com.gongsiradar.data.DataSourceException;
import com.gongsiradar.data.RadarSource;
import com.gongsiradar.data.Rows;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 내부 데이터 API(CONTRACT §11.2) — AI 서버 전용. 인증은 {@link InternalKeyFilter}.
 * <p>
 * <b>응답 모양은 원천 그대로</b>(OpenDART·공공데이터포털 필드, snake_case)다. AI 서버의 radar 파이프라인이 원천을
 * 직접 부르던 때와 같은 값을 받게 해, 그쪽 코드가 바뀌지 않게 한다. 공통 응답 형식(ApiResponse)으로 감싸지 않는다.
 * 데이터가 없으면 404 {@code {"detail": "..."}}(radar는 SourceError로 받는다).
 * <p>
 * 적재 DB를 먼저 읽고 없으면 원천을 부른다(@Primary {@link RadarSource}).
 */
@Slf4j
@RestController
@RequestMapping("/internal/data")
@RequiredArgsConstructor
public class InternalDataController {

    private final RadarSource source;

    @GetMapping("/companies/resolve")
    public Map<String, Object> resolve(@RequestParam String q) {
        Map<String, Object> c = source.resolve(q);
        // 계약 모양으로 맞춘다. OpenDART corpCode.xml에는 업종·시장이 없어 회사 목록(적재 DB)에서 채운다
        Map<String, Object> out = new LinkedHashMap<>(c);
        List<String> keys = List.of("corp_code", "corp_name", "stock_code", "induty", "induty_code", "market");
        if (keys.stream().anyMatch(k -> !out.containsKey(k))) {
            Map<String, Object> listed = source.companies().stream()
                    .filter(x -> java.util.Objects.equals(x.get("corp_code"), c.get("corp_code")))
                    .findFirst().orElse(Map.of());
            for (String k : keys) {
                if (!out.containsKey(k)) out.put(k, listed.get(k));
            }
        }
        return out;
    }

    @GetMapping("/companies")
    public List<Map<String, Object>> companies() {
        return source.companies();
    }

    @GetMapping("/filings")
    public List<Map<String, Object>> filings(@RequestParam String corpCode) {
        return source.filings(corpCode);
    }

    @GetMapping("/report")
    public Map<String, Object> report(@RequestParam String corpCode, @RequestParam int bsnsYear,
                                      @RequestParam String reprtCode) {
        return source.findReport(corpCode, bsnsYear, reprtCode);
    }

    @GetMapping("/documents/{rceptNo}")
    public ResponseEntity<byte[]> document(@PathVariable String rceptNo) {
        if (!rceptNo.matches("\\d{8,20}")) {
            throw new DataSourceException("접수번호 형식이 아닙니다: " + rceptNo);
        }
        return ResponseEntity.ok().contentType(MediaType.parseMediaType("application/zip"))
                .header("Content-Disposition", "attachment; filename=\"" + rceptNo + ".zip\"")
                .body(source.document(rceptNo));
    }

    @GetMapping("/financials")
    public Map<String, Object> financials(@RequestParam String corpCode, @RequestParam int bsnsYear,
                                          @RequestParam String reprtCode) {
        Dart.reprt(reprtCode);
        RadarSource.Financials f = source.financials(corpCode, bsnsYear, reprtCode);
        return Rows.m("fs_div", f.fsDiv(), "list", f.rows());
    }

    @GetMapping("/peers")
    public Map<String, Object> peers(@RequestParam String corpCode, @RequestParam int bsnsYear,
                                     @RequestParam String reprtCode) {
        return Rows.m("list", source.peers(corpCode, bsnsYear, reprtCode));
    }

    @GetMapping("/lawsuits")
    public Map<String, Object> lawsuits(@RequestParam String corpCode, @RequestParam String bgn, @RequestParam String end) {
        return Rows.m("list", source.lawsuits(corpCode, bgn, end));
    }

    @GetMapping("/governance")
    public Map<String, Object> governance(@RequestParam String corpCode, @RequestParam int bsnsYear,
                                          @RequestParam String reprtCode) {
        return source.governance(corpCode, bsnsYear, reprtCode);
    }

    @GetMapping("/market/{stockCode}")
    public Map<String, Object> market(@PathVariable String stockCode) {
        return Rows.m("items", source.market(stockCode));
    }

    /**
     * 이 컨트롤러의 오류는 FastAPI 모양 {@code {"detail": ...}}으로 낸다(공통 응답 형식이 아니다).
     * 전역 처리기보다 먼저 잡도록 순서를 앞에 둔다.
     */
    @RestControllerAdvice(assignableTypes = InternalDataController.class)
    @Order(Ordered.HIGHEST_PRECEDENCE)
    static class Errors {

        @ExceptionHandler(DataSourceException.class)
        ResponseEntity<Map<String, Object>> notFound(DataSourceException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("detail", String.valueOf(e.getMessage())));
        }

        @ExceptionHandler({MissingServletRequestParameterException.class, MethodArgumentTypeMismatchException.class})
        ResponseEntity<Map<String, Object>> badRequest(Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("detail", "요청 형식 오류: " + e.getMessage()));
        }

        @ExceptionHandler(Exception.class)
        ResponseEntity<Map<String, Object>> internal(Exception e) {
            log.error("내부 데이터 API 오류", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("detail", "내부 오류: " + e.getClass().getSimpleName()));
        }
    }
}
