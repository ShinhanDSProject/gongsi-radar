package com.gongsiradar.agent.controller;

import com.gongsiradar.ai.client.AiClient;
import com.gongsiradar.common.response.ApiResponse;
import com.gongsiradar.common.web.CurrentUser;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Agent 목록(Manager + Worker 4종). FastAPI {@code /ai/agents} 프록시.
 * 화면이 "누가 어떤 단계를 맡는가"를 보여 주는 데 쓴다. 실행은 분석 요청 경로로만 한다.
 */
@RestController
@RequestMapping("/api/agents")
@RequiredArgsConstructor
public class AgentController {

    private final AiClient aiClient;

    @GetMapping
    public ApiResponse<Object> list(@AuthenticationPrincipal String userId) {
        return ApiResponse.success(aiClient.agents(userId, CurrentUser.scopes()));
    }
}
