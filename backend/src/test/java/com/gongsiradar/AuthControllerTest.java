package com.gongsiradar;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 로그인·토큰. MariaDB(3307)의 seed 사용자를 그대로 쓴다. */
@SpringBootTest
@AutoConfigureMockMvc
class AuthControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void 로그인_성공하면_access_refresh_토큰과_scope를_준다() throws Exception {
        mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":\"senior_001\",\"password\":\"password\"}"))
                .andExpect(status().isOk())
                .andExpect(header().exists("X-Request-ID"))
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.accessToken", not(emptyOrNullString())))
                .andExpect(jsonPath("$.data.refreshToken", not(emptyOrNullString())))
                .andExpect(jsonPath("$.data.user.role").value("SENIOR_MANAGER"))
                .andExpect(jsonPath("$.data.user.scopes", hasItems("REPORT_WRITE", "PUBLICATION_READ")));
    }

    @Test
    void 비밀번호가_틀리면_401_UNAUTHORIZED() throws Exception {
        mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":\"analyst_001\",\"password\":\"wrong\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
    }

    @Test
    void 토큰_없이_API를_부르면_401과_공통_응답() throws Exception {
        mvc.perform(get("/api/analysis-requests").header("X-Request-ID", "test-uid-1"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("X-Request-ID", "test-uid-1"))
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.requestId").value("test-uid-1"));
    }

    @Test
    void refresh_토큰으로_access_토큰을_다시_받는다() throws Exception {
        String body = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"userId\":\"analyst_001\",\"password\":\"password\"}"))
                .andReturn().getResponse().getContentAsString();
        String refresh = com.jayway.jsonpath.JsonPath.read(body, "$.data.refreshToken");

        mvc.perform(post("/api/auth/refresh").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"refreshToken\":\"" + refresh + "\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.accessToken", not(emptyOrNullString())));

        // refresh 토큰으로는 API를 부를 수 없다
        mvc.perform(get("/api/analysis-requests").header("Authorization", "Bearer " + refresh))
                .andExpect(status().isUnauthorized());
    }
}
