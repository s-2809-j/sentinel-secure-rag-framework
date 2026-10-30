package com.sentinel.document;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sentinel.auth.filter.JwtAuthenticationFilter;
import com.sentinel.auth.service.JwtService;
import com.sentinel.auth.service.UserDetailsServiceImpl;
import com.sentinel.config.SecurityConfig;
import com.sentinel.document.controller.DocumentController;
import com.sentinel.document.dto.DocumentAnalysisResponse;
import com.sentinel.document.dto.DocumentUploadRequest;
import com.sentinel.document.dto.KnowledgeUploadResponse;
import com.sentinel.document.service.DocumentService;
import com.sentinel.fastapi.exception.FastApiException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.doAnswer;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(DocumentController.class)
@Import(SecurityConfig.class)
@DisplayName("DocumentController Slice Tests")
class DocumentControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    // ── The bean under test ───────────────────────────────────────────────
    @MockitoBean
    DocumentService documentService;

    // ── Security chain beans — required by @WebMvcTest + SecurityConfig ──
    @MockitoBean
    JwtService jwtService;

    @MockitoBean
    UserDetailsServiceImpl userDetailsService;

    // ── JwtAuthenticationFilter is a @Component — must be mocked ─────────
    // If your SecurityConfig imports it via constructor, the slice needs it
    @MockitoBean
    JwtAuthenticationFilter jwtAuthenticationFilter;

    @BeforeEach
    void setUp() throws Exception {
        // The mocked JwtAuthenticationFilter must delegate to the filter chain,
        // otherwise requests never reach the DispatcherServlet.
        doAnswer(invocation -> {
            jakarta.servlet.FilterChain chain = invocation.getArgument(2);
            chain.doFilter(invocation.getArgument(0), invocation.getArgument(1));
            return null;
        }).when(jwtAuthenticationFilter)
          .doFilter(any(jakarta.servlet.ServletRequest.class),
                    any(jakarta.servlet.ServletResponse.class),
                    any(jakarta.servlet.FilterChain.class));
    }

    // ─────────────────────────────────────────────────────────────────────
    // FIXTURES
    // ─────────────────────────────────────────────────────────────────────

    private static final String ANALYZE_ENDPOINT = "/api/v1/documents/analyze";
    private static final String UPLOAD_ENDPOINT  = "/api/v1/documents/upload";

    private DocumentUploadRequest sampleRequest() throws java.io.IOException {
        // Must be under the real temp dir: DocumentController.validateFilePath
        // only accepts paths below java.io.tmpdir (resolved with toRealPath()).
        String path = java.nio.file.Path.of(System.getProperty("java.io.tmpdir"))
                .toRealPath()
                .resolve("report.pdf")
                .toString();
        return new DocumentUploadRequest(
                path,
                "report.pdf",
                "pdf",
                "application/pdf",
                102_400L
        );
    }

    private DocumentAnalysisResponse sampleAnalysisResponse() {
        return new DocumentAnalysisResponse(
                UUID.randomUUID().toString(),
                true,
                "Document analyzed successfully.",
                null,
                Instant.now()
        );
    }

    private KnowledgeUploadResponse sampleKnowledgeResponse() {
        return new KnowledgeUploadResponse(
                UUID.randomUUID().toString(),
                true,
                "Document ingested into knowledge base.",
                null,
                Instant.now()
        );
    }

    // ─────────────────────────────────────────────────────────────────────
    // POST /analyze
    // ─────────────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("POST /documents/analyze")
    class AnalyzeTests {

        @Test
        @WithMockUser(username = "analyst@sentinel.io", roles = "ANALYST")
        @DisplayName("200 when ANALYST submits valid document")
        void analyze_returns200ForAnalyst() throws Exception {
            given(documentService.analyzeDocument(any(DocumentUploadRequest.class), any(String.class)))
                    .willReturn(sampleAnalysisResponse());

            mockMvc.perform(post(ANALYZE_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.success").value(true))
                    .andExpect(jsonPath("$.message").value("Document analyzed successfully."))
                    .andExpect(jsonPath("$.requestId").exists());
        }

        @Test
        @WithMockUser(username = "admin@sentinel.io", roles = "ADMIN")
        @DisplayName("200 when ADMIN submits valid document")
        void analyze_returns200ForAdmin() throws Exception {
            given(documentService.analyzeDocument(any(DocumentUploadRequest.class), any(String.class)))
                    .willReturn(sampleAnalysisResponse());

            mockMvc.perform(post(ANALYZE_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isOk());
        }

        @Test
        @WithMockUser(username = "analyst@sentinel.io", roles = "ANALYST")
        @DisplayName("200 when ANALYST submits multipart document analysis")
        void analyze_returns200ForAnalystMultipart() throws Exception {
            given(documentService.analyzeDocument(any(DocumentUploadRequest.class), any(String.class)))
                    .willReturn(sampleAnalysisResponse());

            org.springframework.mock.web.MockMultipartFile mockFile =
                    new org.springframework.mock.web.MockMultipartFile(
                            "file",
                            "report.pdf",
                            MediaType.APPLICATION_PDF_VALUE,
                            "test content".getBytes()
                    );

            mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart(ANALYZE_ENDPOINT)
                            .file(mockFile)
                            .with(csrf()))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.success").value(true))
                    .andExpect(jsonPath("$.message").value("Document analyzed successfully."));
        }

        @Test
        @WithMockUser(username = "viewer@sentinel.io", roles = "VIEWER")
        @DisplayName("403 when VIEWER attempts document analysis — role not permitted")
        void analyze_returns403ForViewer() throws Exception {
            mockMvc.perform(post(ANALYZE_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andDo(org.springframework.test.web.servlet.result.MockMvcResultHandlers.print())
                    .andExpect(status().isForbidden());
        }

        @Test
        @DisplayName("401 when request has no authentication")
        void analyze_returns401ForUnauthenticatedRequest() throws Exception {
            mockMvc.perform(post(ANALYZE_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isUnauthorized());
        }

        @Test
        @WithMockUser(roles = "ANALYST")
        @DisplayName("400 when filePath is blank")
        void analyze_returns400ForBlankFilePath() throws Exception {
            DocumentUploadRequest bad = new DocumentUploadRequest(
                    "", "report.pdf", "pdf", "application/pdf", 1024L);

            mockMvc.perform(post(ANALYZE_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(bad)))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.errorCode").exists());
        }

        @Test
        @WithMockUser(roles = "ANALYST")
        @DisplayName("502 when FastAPI engine is unavailable")
        void analyze_returns502WhenFastApiIsDown() throws Exception {
            given(documentService.analyzeDocument(any(DocumentUploadRequest.class), any(String.class)))
                    .willThrow(new FastApiException("FastAPI unreachable"));

            mockMvc.perform(post(ANALYZE_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isBadGateway());
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // POST /upload
    // ─────────────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("POST /documents/upload")
    class UploadTests {

        @Test
        @WithMockUser(username = "admin@sentinel.io", roles = "ADMIN")
        @DisplayName("200 when ADMIN uploads document to knowledge base")
        void upload_returns200ForAdmin() throws Exception {
            given(documentService.uploadToKnowledge(any(DocumentUploadRequest.class), any(String.class)))
                    .willReturn(sampleKnowledgeResponse());

            mockMvc.perform(post(UPLOAD_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.success").value(true))
                    .andExpect(jsonPath("$.message")
                            .value("Document ingested into knowledge base."));
        }

        @Test
        @WithMockUser(username = "admin@sentinel.io", roles = "ADMIN")
        @DisplayName("200 when ADMIN uploads multipart document to knowledge base")
        void upload_returns200ForAdminMultipart() throws Exception {
            given(documentService.uploadToKnowledge(any(DocumentUploadRequest.class), any(String.class)))
                    .willReturn(sampleKnowledgeResponse());

            org.springframework.mock.web.MockMultipartFile mockFile =
                    new org.springframework.mock.web.MockMultipartFile(
                            "file",
                            "report.pdf",
                            MediaType.APPLICATION_PDF_VALUE,
                            "test content".getBytes()
                    );

            mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart(UPLOAD_ENDPOINT)
                            .file(mockFile)
                            .with(csrf()))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.success").value(true));
        }

        @Test
        @WithMockUser(username = "analyst@sentinel.io", roles = "ANALYST")
        @DisplayName("200 when ANALYST uploads document to knowledge base")
        void upload_returns200ForAnalyst() throws Exception {
            given(documentService.uploadToKnowledge(any(DocumentUploadRequest.class), any(String.class)))
                    .willReturn(sampleKnowledgeResponse());

            mockMvc.perform(post(UPLOAD_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.success").value(true))
                    .andExpect(jsonPath("$.message")
                            .value("Document ingested into knowledge base."));
        }

        @Test
        @WithMockUser(username = "viewer@sentinel.io", roles = "VIEWER")
        @DisplayName("403 when VIEWER attempts upload — ADMIN only endpoint")
        void upload_returns403ForViewer() throws Exception {
            mockMvc.perform(post(UPLOAD_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isForbidden());
        }

        @Test
        @DisplayName("401 when request has no authentication")
        void upload_returns401ForUnauthenticatedRequest() throws Exception {
            mockMvc.perform(post(UPLOAD_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isUnauthorized());
        }

        @Test
        @WithMockUser(roles = "ADMIN")
        @DisplayName("400 when filename is blank")
        void upload_returns400ForBlankFilename() throws Exception {
            DocumentUploadRequest bad = new DocumentUploadRequest(
                    "/path/file.pdf", "", "pdf", "application/pdf", 1024L);

            mockMvc.perform(post(UPLOAD_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(bad)))
                    .andExpect(status().isBadRequest());
        }

        @Test
        @WithMockUser(roles = "ADMIN")
        @DisplayName("502 when FastAPI engine is unavailable during upload")
        void upload_returns502WhenFastApiIsDown() throws Exception {
            given(documentService.uploadToKnowledge(any(DocumentUploadRequest.class), any(String.class)))
                    .willThrow(new FastApiException("FastAPI unreachable during upload"));

            mockMvc.perform(post(UPLOAD_ENDPOINT)
                            .with(csrf())
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(sampleRequest())))
                    .andExpect(status().isBadGateway());
        }
    }
}