package com.sentinel.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sentinel.auth.controller.AuthController;
import com.sentinel.auth.dto.LoginRequest;
import com.sentinel.auth.dto.LoginResponse;
import com.sentinel.auth.dto.RefreshTokenRequest;
import com.sentinel.auth.dto.RegisterRequest;
import com.sentinel.auth.filter.JwtAuthenticationFilter;
import com.sentinel.auth.service.AuthService;
import com.sentinel.auth.service.JwtService;
import com.sentinel.exception.UnauthorizedException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.willDoNothing;
import static org.mockito.BDDMockito.willThrow;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(AuthController.class)
@AutoConfigureMockMvc(addFilters = false)
class AuthControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @MockitoBean
    AuthService authService;

    @MockitoBean
    JwtService jwtService;

    @MockitoBean
    JwtAuthenticationFilter jwtAuthenticationFilter;

    @MockitoBean
    UserDetailsService userDetailsService;

    // Shared fixtures
    private static final String BASE = "/api/v1/auth";

    private LoginResponse sampleLoginResponse() {
        return LoginResponse.of(
                "access-token-stub",
                "refresh-token-stub",
                900L,
                "analyst",
                "ANALYST"
        );
    }

    // ─────────────────────────────────────────────────────────────
    // REGISTER
    // ─────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("POST /register")
    class RegisterTests {

        @Test
        @DisplayName("201 when registration succeeds")
        void register_returns201OnSuccess() throws Exception {
            RegisterRequest body = new RegisterRequest(
                    "analyst",
                    "analyst@sentinel.io",
                    "S3cur3P@ss!"
            );
            willDoNothing().given(authService).register(any(RegisterRequest.class));

            mockMvc.perform(post(BASE + "/register")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(body)))
                    .andExpect(status().isCreated());
        }

        @Test
        @DisplayName("400 when request body fails bean validation — blank username")
        void register_returns400ForBlankUsername() throws Exception {
            RegisterRequest bad = new RegisterRequest(
                    "",
                    "analyst@sentinel.io",
                    "S3cur3P@ss!"
            );

            mockMvc.perform(post(BASE + "/register")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(bad)))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.errorCode").exists());
        }

        @Test
        @DisplayName("400 when request body is completely missing")
        void register_returns400ForMissingBody() throws Exception {
            mockMvc.perform(post(BASE + "/register")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON))
                    .andExpect(status().isBadRequest());
        }
    }

    // ─────────────────────────────────────────────────────────────
    // LOGIN
    // ─────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("POST /login")
    class LoginTests {

        @Test
        @DisplayName("200 with token pair on valid credentials")
        void login_returns200WithTokens() throws Exception {
            LoginRequest body = new LoginRequest("analyst@sentinel.io", "S3cur3P@ss!");
            given(authService.login(any(LoginRequest.class))).willReturn(sampleLoginResponse());

            mockMvc.perform(post(BASE + "/login")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(body)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.accessToken").value("access-token-stub"))
                    .andExpect(jsonPath("$.refreshToken").value("refresh-token-stub"));
        }

        @Test
        @DisplayName("401 when AuthService throws UnauthorizedException")
        void login_returns401OnBadCredentials() throws Exception {
            LoginRequest body = new LoginRequest("analyst@sentinel.io", "wrong-password");
            given(authService.login(any(LoginRequest.class)))
                    .willThrow(new UnauthorizedException("Invalid credentials"));

            mockMvc.perform(post(BASE + "/login")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(body)))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));
        }

        @Test
        @DisplayName("400 when password is blank")
        void login_returns400ForBlankPassword() throws Exception {
            LoginRequest bad = new LoginRequest("analyst@sentinel.io", "");

            mockMvc.perform(post(BASE + "/login")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(bad)))
                    .andExpect(status().isBadRequest());
        }
    }

    // ─────────────────────────────────────────────────────────────
    // REFRESH
    // ─────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("POST /refresh")
    class RefreshTests {

        @Test
        @DisplayName("200 with new token pair on valid refresh token")
        void refresh_returns200WithNewTokens() throws Exception {
            RefreshTokenRequest body = new RefreshTokenRequest("valid-refresh-token");
            given(authService.refresh(any(RefreshTokenRequest.class))).willReturn(sampleLoginResponse());

            mockMvc.perform(post(BASE + "/refresh")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(body)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.accessToken").value("access-token-stub"));
        }

        @Test
        @DisplayName("401 when refresh token is expired or revoked")
        void refresh_returns401ForExpiredToken() throws Exception {
            RefreshTokenRequest body = new RefreshTokenRequest("expired-token");
            given(authService.refresh(any(RefreshTokenRequest.class)))
                    .willThrow(new UnauthorizedException("Refresh token expired"));

            mockMvc.perform(post(BASE + "/refresh")
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(body)))
                    .andExpect(status().isUnauthorized());
        }
    }

    // ─────────────────────────────────────────────────────────────
    // LOGOUT
    // ─────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("POST /logout")
    class LogoutTests {

        @Test
        @WithMockUser(username = "analyst@sentinel.io", roles = "ANALYST")
        @DisplayName("204 when logout succeeds for authenticated user")
        void logout_returns204OnSuccess() throws Exception {
            willDoNothing().given(authService).logout(any());

            mockMvc.perform(post(BASE + "/logout")
                            .with(csrf()))
                    .andExpect(status().isNoContent());
        }

//        @Test
//        @DisplayName("401 when logout is called without authentication")
//        void logout_returns401ForUnauthenticatedRequest() throws Exception {
//            mockMvc.perform(post(BASE + "/logout")
//                            .with(csrf()))
//                    .andExpect(status().isUnauthorized());
//        }
    }
}
