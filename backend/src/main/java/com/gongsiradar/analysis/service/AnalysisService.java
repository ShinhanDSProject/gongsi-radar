package com.gongsiradar.analysis.service;

import com.gongsiradar.analysis.repository.AnalysisRequest;
import com.gongsiradar.analysis.repository.AnalysisRequestStatus;
import com.gongsiradar.analysis.repository.AnalysisRequestRepository;

import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.ai.dto.AiAnalysisRequest;
import com.gongsiradar.ai.dto.AiJobStatus;
import com.gongsiradar.analysis.dto.AnalysisRequestDto;
import com.gongsiradar.analysis.dto.CreateAnalysisRequest;
import com.gongsiradar.analysis.dto.ExecuteResponse;
import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.common.web.RequestContext;
import com.gongsiradar.report.repository.AnalysisReport;
import com.gongsiradar.report.repository.AnalysisReportRepository;
import com.gongsiradar.report.service.ReportService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Slf4j
@Service
@RequiredArgsConstructor
public class AnalysisService {

    /**
     * AI 서버로 넘기는 Scope. Tool Gateway가 검사하는 데이터 Scope만 싣는다.
     * REPORT_READ·REPORT_WRITE는 Spring 화면 권한이라 Agent에게 줄 이유가 없다.
     */
    private static final Set<String> TOOL_SCOPES =
            Set.of("DISCLOSURE_READ", "MARKET_DATA_READ", "RAG_READ", "PUBLICATION_READ");

    private final AnalysisRequestRepository repository;
    private final AnalysisReportRepository reportRepository;
    private final ReportService reportService;
    private final AiClient aiClient;
    private final AuditService auditService;

    @Transactional
    public AnalysisRequestDto create(String userId, List<String> userScopes, CreateAnalysisRequest req) {
        List<String> scope = userScopes.stream().filter(TOOL_SCOPES::contains).sorted().toList();
        AnalysisRequest entity = AnalysisRequest.builder()
                .userId(userId)
                .company(req.company().trim())
                .bsnsYear(req.bsnsYear())
                .reprtCode(req.reprtCode())
                .query(req.query() == null || req.query().isBlank() ? null : req.query())
                .scope(scope)
                .demoFaultInjection(Boolean.TRUE.equals(req.demoFaultInjection()))
                .status(AnalysisRequestStatus.CREATED)
                .requestUid(RequestContext.get())
                .build();
        AnalysisRequest saved = repository.save(entity);
        // 사람이 낸 요청은 Spring Boot가 남긴다. Agent의 실행 기록은 FastAPI 몫이다.
        // 질문 원문은 넣지 않는다 — 입력 가드레일을 거치기 전의 텍스트라 PII가 있을 수 있다
        auditService.record("ANALYSIS_REQUEST_CREATED", userId, null, saved.getId(), Map.of(
                "company", saved.getCompany(), "bsnsYear", saved.getBsnsYear(),
                "reprtCode", saved.getReprtCode(), "scope", scope,
                "hasQuery", saved.getQuery() != null,
                "demoFaultInjection", saved.isDemoFaultInjection()));
        return AnalysisRequestDto.of(saved, null);
    }

    @Transactional(readOnly = true)
    public Page<AnalysisRequestDto> list(String userId, boolean senior, AnalysisRequestStatus status,
                                         Pageable pageable) {
        return repository.search(senior ? null : userId, status, pageable)
                .map(r -> AnalysisRequestDto.of(r, reportIdOf(r)));
    }

    @Transactional(readOnly = true)
    public AnalysisRequestDto get(Long id, String userId, boolean senior) {
        AnalysisRequest r = findReadable(id, userId, senior);
        return AnalysisRequestDto.of(r, reportIdOf(r));
    }

    /**
     * 실행. 입력 가드레일이 막으면(AI 422) 요청을 BLOCKED로 남기고 그대로 422를 돌려준다.
     * <p>
     * {@code noRollbackFor}: BLOCKED 표시는 예외를 던지면서도 커밋돼야 한다.
     * 그 밖의 실패(AI 서버 다운·Kill Switch)에서는 엔티티를 건드리지 않으므로 CREATED 그대로 남아 다시 실행할 수 있다.
     */
    @Transactional(noRollbackFor = ApiException.class)
    public ExecuteResponse execute(Long id, String userId, List<String> userScopes) {
        AnalysisRequest r = findOwned(id, userId);
        if (r.getStatus() != AnalysisRequestStatus.CREATED) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,
                    "이미 실행되었거나 완료된 요청: " + r.getStatus());
        }

        Map<String, Object> options = new HashMap<>();
        options.put("demoFaultInjection", r.isDemoFaultInjection());
        AiAnalysisRequest aiReq = new AiAnalysisRequest(
                r.getId(), userId, r.getCompany(), r.getBsnsYear(), r.getReprtCode(),
                r.getQuery(), r.getScope(), options);

        AiJobStatus job;
        try {
            job = aiClient.startAnalysis(aiReq, userScopes);
        } catch (ApiException e) {
            if (e.getErrorCode() == ErrorCode.GUARDRAIL_BLOCKED) {
                r.markBlocked(RequestContext.get());
                Map<String, Object> payload = new HashMap<>();
                payload.put("stage", "INPUT");
                payload.put("details", e.getDetails());
                auditService.record("GUARDRAIL_BLOCKED", userId, null, r.getId(), payload);
            }
            throw e;
        }
        if (job == null || job.jobId() == null) {
            throw new ApiException(ErrorCode.LLM_PROVIDER_ERROR, "AI 서버가 Job ID를 주지 않았다");
        }

        r.markRunning(job.jobId(), RequestContext.get());
        auditService.record("ANALYSIS_EXECUTED", userId, null, r.getId(),
                Map.of("jobId", job.jobId()));
        return new ExecuteResponse(r.getId(), job.jobId(), r.getStatus());
    }

    /**
     * Job 상세(진행 단계·Timeline)를 화면에 내보낸다.
     * FastAPI를 직접 열지 않고 여기서 프록시하는 이유: 프런트가 아는 서버는 Spring 하나다.
     * 내부 키(X-Internal-API-Key)가 브라우저에 나가는 순간 내부망 경계가 사라진다.
     */
    @Transactional(readOnly = true)
    public AiJobStatus jobDetail(Long id, String userId, boolean senior, List<String> userScopes) {
        AnalysisRequest r = findReadable(id, userId, senior);
        if (r.getJobId() == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "아직 실행되지 않은 요청");
        }
        return aiClient.getJob(r.getJobId(), userId, userScopes);
    }

    /**
     * 폴링. RUNNING이면 AI Job을 확인해 COMPLETED면 리포트를 저장하고, FAILED면 실패로 닫는다.
     * 회사 고유번호·이름은 AI가 확정한 값(report.meta.company)으로 채운다.
     */
    @Transactional
    public AnalysisRequestDto refreshStatus(Long id, String userId, boolean senior, List<String> userScopes) {
        AnalysisRequest r = findReadable(id, userId, senior);
        if (r.getStatus() == AnalysisRequestStatus.RUNNING && r.getJobId() != null) {
            AiJobStatus job;
            try {
                job = aiClient.getJob(r.getJobId(), r.getUserId(), userScopes);
            } catch (ApiException e) {
                if (e.getErrorCode() == ErrorCode.NOT_FOUND) {
                    // AI 서버가 재시작돼 메모리의 Job이 사라진 경우. 다시는 완료되지 않으므로 실패로 닫는다
                    r.markFailed();
                    auditService.record("ANALYSIS_COMPLETED", r.getUserId(), null, r.getId(),
                            Map.of("status", "FAILED", "jobId", r.getJobId(), "error", "JOB_NOT_FOUND"));
                    return AnalysisRequestDto.of(r, reportIdOf(r));
                }
                throw e;
            }
            if ("COMPLETED".equals(job.status())) {
                complete(r, job);
            } else if ("FAILED".equals(job.status())) {
                r.markFailed();
                Object error = job.result() == null ? null : job.result().get("error");
                auditService.record("ANALYSIS_COMPLETED", r.getUserId(), null, r.getId(),
                        Map.of("status", "FAILED", "jobId", r.getJobId(),
                                "error", error == null ? "" : String.valueOf(error)));
            }
            // RUNNING은 그대로
        }
        return AnalysisRequestDto.of(r, reportIdOf(r));
    }

    private void complete(AnalysisRequest r, AiJobStatus job) {
        Object reportObj = job.result() == null ? null : job.result().get("report");
        if (!(reportObj instanceof Map<?, ?> report)) {
            log.warn("COMPLETED인데 result.report가 없다 job={}", job.jobId());
            r.markFailed();
            auditService.record("ANALYSIS_COMPLETED", r.getUserId(), null, r.getId(),
                    Map.of("status", "FAILED", "jobId", job.jobId(), "error", "NO_REPORT"));
            return;
        }
        String corpCode = null;
        String corpName = null;
        if (report.get("meta") instanceof Map<?, ?> meta && meta.get("company") instanceof Map<?, ?> company) {
            corpCode = company.get("corp_code") == null ? null : String.valueOf(company.get("corp_code"));
            corpName = company.get("corp_name") == null ? null : String.valueOf(company.get("corp_name"));
        }
        r.markCompleted(corpCode, corpName);
        AnalysisReport saved = reportService.saveFromAiResult(r, report);
        auditService.record("ANALYSIS_COMPLETED", r.getUserId(), null, r.getId(), Map.of(
                "status", "COMPLETED", "jobId", job.jobId(), "reportId", saved.getId(),
                "corpCode", corpCode == null ? "" : corpCode));
    }

    // ── 접근 검사 ──

    /** 읽기: Junior는 자기 것만, Senior는 전체. */
    private AnalysisRequest findReadable(Long id, String userId, boolean senior) {
        AnalysisRequest r = repository.findById(id)
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "요청을 찾을 수 없음"));
        if (!senior && !r.getUserId().equals(userId)) {
            throw new ApiException(ErrorCode.FORBIDDEN, "타인의 요청에 접근 불가");
        }
        return r;
    }

    /** 실행: 요청한 본인만. Senior라도 남의 분석을 대신 돌리지 않는다 — 실행 기록의 주인이 흐려진다. */
    private AnalysisRequest findOwned(Long id, String userId) {
        AnalysisRequest r = repository.findById(id)
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "요청을 찾을 수 없음"));
        if (!r.getUserId().equals(userId)) {
            throw new ApiException(ErrorCode.FORBIDDEN, "타인의 요청에 접근 불가");
        }
        return r;
    }

    private Long reportIdOf(AnalysisRequest r) {
        if (r.getStatus() != AnalysisRequestStatus.COMPLETED) {
            return null;
        }
        return reportRepository.findByRequestId(r.getId()).map(AnalysisReport::getId).orElse(null);
    }
}
