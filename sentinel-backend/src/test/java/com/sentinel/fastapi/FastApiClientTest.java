package com.sentinel.fastapi;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;
import com.sentinel.fastapi.client.FastApiClient;
import com.sentinel.fastapi.dto.FastApiChatRequest;
import com.sentinel.fastapi.dto.FastApiChatResponse;
import com.sentinel.fastapi.dto.FastApiDocumentRequest;
import com.sentinel.fastapi.dto.FastApiDocumentResponse;
import com.sentinel.fastapi.exception.FastApiException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@ActiveProfiles("test")
@DisplayName("FastApiClient Integration Tests — WireMock")
class FastApiClientTest {

    static WireMockServer wireMock = new WireMockServer(wireMockConfig().dynamicPort());

    static {
        wireMock.start();
        WireMock.configureFor("localhost", wireMock.port());
    }

    private static final String SERVICE_TOKEN = "test-fastapi-service-token";

    @DynamicPropertySource
    static void overrideFastApiBaseUrl(DynamicPropertyRegistry registry) {
        registry.add("fastapi.base-url", () -> "http://localhost:" + wireMock.port());
        registry.add("fastapi.service-token", () -> SERVICE_TOKEN);
    }

    @Autowired
    FastApiClient fastApiClient;

    @BeforeEach
    void resetWireMock() {
        wireMock.resetAll();
    }

    // ─────────────────────────────────────────────────────────────
    // CHAT
    // ─────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("FastApiClient.chat()")
    class ChatTests {

        // Update this if your FastApiClient now calls /v1/chat
        private static final String CHAT_PATH = "/v1/chat";

        @Test
        @DisplayName("Returns FastApiChatResponse when FastAPI returns 200")
        void chat_returns200Response() {

            wireMock.stubFor(post(urlEqualTo(CHAT_PATH))
                    .willReturn(aResponse()
                            .withStatus(200)
                            .withHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                            .withBody("""
                            {
                                "success": true,
                                "workflow": "chat",
                                "request_id": "req-001",
                                "message": "Threat analysis complete.",
                                "data": null
                            }
                            """)));

            FastApiChatRequest request =
                    FastApiChatRequest.of(
                            "What is the threat?",
                            "req-001",
                            "test-user",
                            "test-session"
                    );

            FastApiChatResponse response = fastApiClient.chat(request);

            assertThat(response.success()).isTrue();
            assertThat(response.workflow()).isEqualTo("chat");
            assertThat(response.requestId()).isEqualTo("req-001");
            assertThat(response.message()).isEqualTo("Threat analysis complete.");
        }

        @Test
        @DisplayName("Request body includes query, request_id, user_id and session_id")
        void chat_sendsCorrectRequestBody() {

            wireMock.stubFor(post(urlEqualTo(CHAT_PATH))
                    .withHeader("X-Service-Token", equalTo(SERVICE_TOKEN))
                    .withRequestBody(matchingJsonPath("$.query", equalTo("Test query")))
                    .withRequestBody(matchingJsonPath("$.request_id", equalTo("req-abc")))
                    .withRequestBody(matchingJsonPath("$.user_id", equalTo("test-user")))
                    .withRequestBody(matchingJsonPath("$.session_id", equalTo("test-session")))
                    .willReturn(aResponse()
                            .withStatus(200)
                            .withHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                            .withBody("""
                            {
                                "success": true,
                                "workflow": "chat",
                                "request_id": "req-abc",
                                "message": "ok",
                                "data": null
                            }
                            """)));

            FastApiChatRequest request =
                    FastApiChatRequest.of(
                            "Test query",
                            "req-abc",
                            "test-user",
                            "test-session"
                    );

            FastApiChatResponse response = fastApiClient.chat(request);

            assertThat(response.success()).isTrue();

            wireMock.verify(postRequestedFor(urlEqualTo(CHAT_PATH))
                    .withRequestBody(matchingJsonPath("$.query", equalTo("Test query")))
                    .withRequestBody(matchingJsonPath("$.request_id", equalTo("req-abc")))
                    .withRequestBody(matchingJsonPath("$.user_id", equalTo("test-user")))
                    .withRequestBody(matchingJsonPath("$.session_id", equalTo("test-session"))));
        }

        @Test
        @DisplayName("Throws FastApiException when FastAPI returns 500")
        void chat_throwsFastApiExceptionOn500() {

            wireMock.stubFor(post(urlEqualTo(CHAT_PATH))
                    .willReturn(aResponse().withStatus(500)));

            FastApiChatRequest request =
                    FastApiChatRequest.of(
                            "Boom query",
                            "req-err",
                            "test-user",
                            "test-session"
                    );

            assertThatThrownBy(() -> fastApiClient.chat(request))
                    .isInstanceOf(FastApiException.class);
        }

        @Test
        @DisplayName("Throws FastApiException when FastAPI returns 422")
        void chat_throwsFastApiExceptionOn422() {

            wireMock.stubFor(post(urlEqualTo(CHAT_PATH))
                    .willReturn(aResponse().withStatus(422)));

            FastApiChatRequest request =
                    FastApiChatRequest.of(
                            "Bad input",
                            "req-422",
                            "test-user",
                            "test-session"
                    );

            assertThatThrownBy(() -> fastApiClient.chat(request))
                    .isInstanceOf(FastApiException.class);
        }

        @Test
        @DisplayName("Throws FastApiException when FastAPI returns 503")
        void chat_throwsFastApiExceptionOn503() {

            wireMock.stubFor(post(urlEqualTo(CHAT_PATH))
                    .willReturn(aResponse().withStatus(503)));

            FastApiChatRequest request =
                    FastApiChatRequest.of(
                            "No service",
                            "req-503",
                            "test-user",
                            "test-session"
                    );

            assertThatThrownBy(() -> fastApiClient.chat(request))
                    .isInstanceOf(FastApiException.class);
        }
    }

    // ─────────────────────────────────────────────────────────────
    // ANALYZE DOCUMENT
    // ─────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("FastApiClient.analyzeDocument()")
    class AnalyzeDocumentTests {

        private static final String ANALYZE_PATH = "/v1/documents/analyze";

        private FastApiDocumentRequest sampleDocumentRequest() {
            return new FastApiDocumentRequest(
                    "req-doc-001",
                    "/uploads/report.pdf",
                    "report.pdf",
                    "pdf",
                    "application/pdf",
                    102_400L,
                    null,
                    "test-user"
            );
        }

        @Test
        @DisplayName("Returns FastApiDocumentResponse when FastAPI returns 200")
        void analyzeDocument_returns200Response() {
            wireMock.stubFor(post(urlEqualTo(ANALYZE_PATH))
                    .willReturn(aResponse()
                            .withStatus(200)
                            .withHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                            .withBody("""
                                {
                                    "success": true,
                                    "workflow": "analyze",
                                    "request_id": "req-doc-001",
                                    "message": "Analysis complete.",
                                    "data": null
                                }
                                """)));

            FastApiDocumentResponse response = fastApiClient.analyzeDocument(sampleDocumentRequest());

            assertThat(response.success()).isTrue();
            assertThat(response.workflow()).isEqualTo("analyze");
            assertThat(response.requestId()).isEqualTo("req-doc-001");
        }

        @Test
        @DisplayName("Request body includes file_path, metadata, request_id, and workflow")
        void analyzeDocument_sendsCorrectRequestBody() {
            wireMock.stubFor(post(urlEqualTo(ANALYZE_PATH))
                    .withRequestBody(matchingJsonPath("$.request_id", equalTo("req-doc-001")))
                    .withRequestBody(matchingJsonPath("$.file_path", equalTo("/uploads/report.pdf")))
                    .withRequestBody(matchingJsonPath("$.filename", equalTo("report.pdf")))
                    .withRequestBody(matchingJsonPath("$.extension", equalTo("pdf")))
                    .withRequestBody(matchingJsonPath("$.mime_type", equalTo("application/pdf")))
                    .withRequestBody(matchingJsonPath("$.size_bytes", equalTo("102400")))
                    .withRequestBody(matchingJsonPath("$.user_id", equalTo("test-user")))
                    .willReturn(aResponse()
                            .withStatus(200)
                            .withHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                            .withBody("""
                                {
                                    "success": true,
                                    "workflow": "analyze",
                                    "request_id": "req-doc-001",
                                    "message": "ok",
                                    "data": null
                                }
                                """)));

            fastApiClient.analyzeDocument(sampleDocumentRequest());

            wireMock.verify(postRequestedFor(urlEqualTo(ANALYZE_PATH))
                    .withRequestBody(matchingJsonPath("$.request_id"))
                    .withRequestBody(matchingJsonPath("$.file_path"))
                    .withRequestBody(matchingJsonPath("$.filename"))
                    .withRequestBody(matchingJsonPath("$.extension"))
                    .withRequestBody(matchingJsonPath("$.mime_type"))
                    .withRequestBody(matchingJsonPath("$.size_bytes"))
                    .withRequestBody(matchingJsonPath("$.user_id")));
        }

        @Test
        @DisplayName("Throws FastApiException on 500 from analyze endpoint")
        void analyzeDocument_throwsFastApiExceptionOn500() {
            wireMock.stubFor(post(urlEqualTo(ANALYZE_PATH))
                    .willReturn(aResponse().withStatus(500)));

            assertThatThrownBy(() -> fastApiClient.analyzeDocument(sampleDocumentRequest()))
                    .isInstanceOf(FastApiException.class);
        }
    }

    // ─────────────────────────────────────────────────────────────
    // UPLOAD DOCUMENT
    // ─────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("FastApiClient.uploadDocument()")
    class UploadDocumentTests {

        private static final String UPLOAD_PATH = "/v1/documents/upload";

        private FastApiDocumentRequest sampleUploadRequest() {
            return new FastApiDocumentRequest(
                    "req-upload-001",
                    "/uploads/threat-model.pdf",
                    "threat-model.pdf",
                    "pdf",
                    "application/pdf",
                    204_800L,
                    null,
                    "test-user"
            );
        }

        @Test
        @DisplayName("Returns FastApiDocumentResponse when FastAPI returns 200")
        void uploadDocument_returns200Response() {
            wireMock.stubFor(post(urlEqualTo(UPLOAD_PATH))
                    .willReturn(aResponse()
                            .withStatus(200)
                            .withHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                            .withBody("""
                                {
                                    "success": true,
                                    "workflow": "knowledge_upload",
                                    "request_id": "req-upload-001",
                                    "message": "Ingested into knowledge base.",
                                    "ingestion_result": {
                                        "status": "SUCCESS",
                                        "success": true,
                                        "document_id": null,
                                        "chunk_count": 3,
                                        "embedding_count": 3,
                                        "message": "Document successfully ingested."
                                    }
                                }
                                """)));

            FastApiDocumentResponse response = fastApiClient.uploadDocument(sampleUploadRequest());

            assertThat(response.success()).isTrue();
            assertThat(response.message()).isEqualTo("Ingested into knowledge base.");
            assertThat(response.ingestionResult()).isNotNull();
        }

        @Test
        @DisplayName("Throws FastApiException on 500 from upload endpoint")
        void uploadDocument_throwsFastApiExceptionOn500() {
            wireMock.stubFor(post(urlEqualTo(UPLOAD_PATH))
                    .willReturn(aResponse().withStatus(500)));

            assertThatThrownBy(() -> fastApiClient.uploadDocument(sampleUploadRequest()))
                    .isInstanceOf(FastApiException.class);
        }

        @Test
        @DisplayName("Throws FastApiException on 404 — upload endpoint not found")
        void uploadDocument_throwsFastApiExceptionOn404() {
            wireMock.stubFor(post(urlEqualTo(UPLOAD_PATH))
                    .willReturn(aResponse().withStatus(404)));

            assertThatThrownBy(() -> fastApiClient.uploadDocument(sampleUploadRequest()))
                    .isInstanceOf(FastApiException.class);
        }
    }
}