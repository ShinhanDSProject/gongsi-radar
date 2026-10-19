package com.gongsiradar.glossary.service;

import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.ai.dto.GlossaryDraft;
import com.gongsiradar.ai.dto.GuardrailCheckResult;
import com.gongsiradar.audit.service.AuditService;
import com.gongsiradar.common.exception.ApiException;
import com.gongsiradar.common.exception.ErrorCode;
import com.gongsiradar.glossary.dto.GlossaryDecisionRequest;
import com.gongsiradar.glossary.dto.GlossaryTermDto;
import com.gongsiradar.glossary.dto.GlossaryTermRequest;
import com.gongsiradar.glossary.repository.GlossaryTerm;
import com.gongsiradar.glossary.repository.GlossaryTermRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 용어집(#14). 리포트 발행과 같은 규칙으로 다룬다 — 누구나 초안을 쓰고 검토를 요청할 수 있지만,
 * 게시는 결재자만, 자기가 요청한 건은 승인할 수 없다. 정의 문장은 요청·승인 때 출력 필터를 거친다.
 */
@Service
@RequiredArgsConstructor
public class GlossaryService {

    private final GlossaryTermRepository repository;
    private final AiClient aiClient;
    private final AuditService auditService;

    @Transactional(readOnly = true)
    public List<GlossaryTermDto> published() {
        return repository.findByStatusOrderByTermAsc(GlossaryTerm.PUBLISHED).stream().map(GlossaryTermDto::of).toList();
    }

    @Transactional(readOnly = true)
    public List<GlossaryTermDto> all(String status) {
        List<GlossaryTerm> rows = status == null || status.isBlank()
                ? repository.findAllByOrderByUpdatedAtDesc()
                : repository.findAllByOrderByUpdatedAtDesc().stream().filter(t -> status.equals(t.getStatus())).toList();
        return rows.stream().map(GlossaryTermDto::of).toList();
    }

    @Transactional
    public GlossaryTermDto create(String userId, GlossaryTermRequest req) {
        String term = req.term().strip();
        if (repository.findByTerm(term).isPresent()) {
            throw new ApiException(ErrorCode.GLOSSARY_CONFLICT, "이미 있는 용어입니다: " + term);
        }
        GlossaryTerm t = repository.saveAndFlush(GlossaryTerm.builder()
                .term(term).aliases(csv(req.aliases())).definition(req.definition().strip())
                .usageNote(blankToNull(req.usageNote())).related(csv(req.related())).source(blankToNull(req.source()))
                .status(GlossaryTerm.DRAFT).aiDrafted(false).createdBy(userId).build());
        auditService.record("GLOSSARY_CREATED", userId, Map.of("termId", t.getId(), "term", term));
        return GlossaryTermDto.of(t);
    }

    @Transactional
    public GlossaryTermDto update(Long id, String userId, boolean senior, GlossaryTermRequest req) {
        GlossaryTerm t = find(id);
        if (!t.editable()) {
            throw new ApiException(ErrorCode.GLOSSARY_CONFLICT, "작성 중이거나 반려된 용어만 고칠 수 있습니다",
                    Map.of("status", t.getStatus()));
        }
        requireOwnerOrSenior(t, userId, senior);
        String term = req.term().strip();
        repository.findByTerm(term).filter(o -> !o.getId().equals(id)).ifPresent(o -> {
            throw new ApiException(ErrorCode.GLOSSARY_CONFLICT, "이미 있는 용어입니다: " + term);
        });
        boolean definitionChanged = !Objects.equals(t.getDefinition(), req.definition().strip());
        t.edit(term, csv(req.aliases()), req.definition().strip(), blankToNull(req.usageNote()), csv(req.related()),
                blankToNull(req.source()), t.isAiDrafted() && !definitionChanged);   // 사람이 정의를 고치면 AI 초안 표시를 뗀다
        auditService.record("GLOSSARY_EDITED", userId, Map.of("termId", id, "term", term));
        return GlossaryTermDto.of(t);
    }

    /** AI가 쓴 정의 초안을 넣는다. 게시는 여전히 사람 검토를 거친다. */
    /**
     * LLM이 정의 초안을 쓰고 ai_drafted 표시를 단다. 상태는 그대로(작성 중·반려) — 사람이 고치고 검토를 요청해야 게시된다.
     * mock이면 초안을 쓰지 않고 그대로 돌려준다(정의를 지어내지 않는다).
     */
    @Transactional
    public GlossaryTermDto aiDraft(Long id, String userId, boolean senior) {
        GlossaryTerm t = find(id);
        if (!t.editable()) {
            throw new ApiException(ErrorCode.GLOSSARY_CONFLICT, "작성 중이거나 반려된 용어만 고칠 수 있습니다",
                    Map.of("status", t.getStatus()));
        }
        requireOwnerOrSenior(t, userId, senior);
        String context = t.getDefinition() == null || t.getDefinition().isBlank() ? null
                : t.getDefinition().substring(0, Math.min(500, t.getDefinition().length()));
        GlossaryDraft d = aiClient.glossaryDraft(t.getTerm(), GlossaryTermDto.split(t.getAliases()), context, userId);
        if (d == null || d.mock() || d.definition() == null || d.definition().isBlank()) {
            throw new ApiException(ErrorCode.LLM_PROVIDER_ERROR, "LLM이 mock 상태라 초안을 만들지 않았습니다. 직접 작성해 주세요",
                    Map.of("mock", d != null && d.mock()));
        }
        String usage = d.usageNote() == null || d.usageNote().isBlank() ? t.getUsageNote() : d.usageNote();
        t.edit(t.getTerm(), t.getAliases(), d.definition(), usage, t.getRelated(), t.getSource(), true);
        auditService.record("GLOSSARY_AI_DRAFTED", userId, Map.of("termId", id, "term", t.getTerm(), "model", String.valueOf(d.model())));
        return GlossaryTermDto.of(t);
    }


    @Transactional
    public GlossaryTermDto submit(Long id, String userId, boolean senior) {
        GlossaryTerm t = find(id);
        if (!t.editable()) {
            throw new ApiException(ErrorCode.GLOSSARY_CONFLICT, "이미 검토 중이거나 게시된 용어입니다",
                    Map.of("status", t.getStatus()));
        }
        requireOwnerOrSenior(t, userId, senior);
        checkText(t, userId, "GLOSSARY_SUBMIT");
        t.submit(userId);
        auditService.record("GLOSSARY_SUBMITTED", userId, Map.of("termId", id, "term", t.getTerm()));
        return GlossaryTermDto.of(t);
    }

    @Transactional
    public GlossaryTermDto approve(Long id, String userId, GlossaryDecisionRequest req) {
        GlossaryTerm t = pendingNotMine(id, userId);
        checkText(t, userId, "GLOSSARY_APPROVE");   // 요청 뒤 필터 기준이 바뀌었을 수 있어 게시 직전에 다시 본다
        t.decide(GlossaryTerm.PUBLISHED, userId, req == null ? null : blankToNull(req.comment()));
        auditService.record("GLOSSARY_APPROVED", userId, Map.of("termId", id, "term", t.getTerm()));
        return GlossaryTermDto.of(t);
    }

    @Transactional
    public GlossaryTermDto reject(Long id, String userId, GlossaryDecisionRequest req) {
        String reason = req == null ? null : blankToNull(req.comment());
        if (reason == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "반려 사유를 적어 주세요");
        }
        GlossaryTerm t = pendingNotMine(id, userId);
        t.decide(GlossaryTerm.REJECTED, userId, reason);
        auditService.record("GLOSSARY_REJECTED", userId, Map.of("termId", id, "term", t.getTerm()));
        return GlossaryTermDto.of(t);
    }

    @Transactional
    public GlossaryTermDto unpublish(Long id, String userId) {
        GlossaryTerm t = find(id);
        if (!GlossaryTerm.PUBLISHED.equals(t.getStatus())) {
            throw new ApiException(ErrorCode.GLOSSARY_CONFLICT, "게시된 용어만 게시를 취소할 수 있습니다",
                    Map.of("status", t.getStatus()));
        }
        t.unpublish();
        auditService.record("GLOSSARY_UNPUBLISHED", userId, Map.of("termId", id, "term", t.getTerm()));
        return GlossaryTermDto.of(t);
    }

    public GlossaryTerm find(Long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ApiException(ErrorCode.NOT_FOUND, "용어를 찾을 수 없습니다: " + id));
    }

    private GlossaryTerm pendingNotMine(Long id, String userId) {
        GlossaryTerm t = find(id);
        if (!GlossaryTerm.PENDING.equals(t.getStatus())) {
            throw new ApiException(ErrorCode.GLOSSARY_CONFLICT, "검토 대기 중인 용어만 승인·반려할 수 있습니다",
                    Map.of("status", t.getStatus()));
        }
        if (userId.equals(t.getSubmittedBy())) {
            throw new ApiException(ErrorCode.SELF_APPROVAL_FORBIDDEN, "자기가 검토를 요청한 용어는 다른 결재자가 결정해야 합니다");
        }
        return t;
    }

    private void requireOwnerOrSenior(GlossaryTerm t, String userId, boolean senior) {
        if (!senior && !userId.equals(t.getCreatedBy())) {
            throw new ApiException(ErrorCode.FORBIDDEN, "작성자나 결재자만 고칠 수 있습니다");
        }
    }

    /** 정의·쓰이는 곳 문장을 출력 필터에 통과시킨다. 막히면 감사 로그를 남기고 거절한다. */
    private void checkText(GlossaryTerm t, String userId, String stage) {
        String text = t.getDefinition() + (t.getUsageNote() == null ? "" : "\n" + t.getUsageNote());
        GuardrailCheckResult check = aiClient.outputCheck(text, userId, Map.of("kind", "glossary", "termId", t.getId()));
        if (check == null || check.blocked()) {
            Map<String, Object> payload = new HashMap<>();
            payload.put("stage", stage);
            payload.put("termId", t.getId());
            payload.put("riskLevel", check == null ? null : check.riskLevel());
            payload.put("detectedIssues", check == null ? List.of() : check.detectedIssues());
            auditService.record("GUARDRAIL_BLOCKED", userId, payload);
            Map<String, Object> details = new HashMap<>();
            details.put("riskLevel", check == null ? null : check.riskLevel());
            details.put("detectedIssues", check == null ? List.of() : check.detectedIssues());
            throw new ApiException(ErrorCode.GUARDRAIL_BLOCKED, "정의에 사용할 수 없는 표현이 포함되어 있습니다", details);
        }
    }

    static String csv(List<String> items) {
        if (items == null) return null;
        String s = items.stream().filter(Objects::nonNull).map(String::strip).filter(x -> !x.isEmpty())
                .map(x -> x.replace(",", " ")).distinct().collect(Collectors.joining(","));
        return s.isEmpty() ? null : s;
    }

    static String blankToNull(String s) {
        return s == null || s.isBlank() ? null : s.strip();
    }
}
