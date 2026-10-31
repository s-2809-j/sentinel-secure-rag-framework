package com.sentinel.document.controller;

import com.sentinel.auth.model.User;
import com.sentinel.document.dto.DocumentAnalysisResponse;
import com.sentinel.document.dto.DocumentUploadRequest;
import com.sentinel.document.dto.KnowledgeUploadResponse;
import com.sentinel.document.service.DocumentService;
import com.sentinel.exception.ForbiddenException;
import com.sentinel.exception.SentinelException;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

@RestController
@RequestMapping("/api/v1/documents")
@RequiredArgsConstructor
@Slf4j
public class DocumentController {

    private final DocumentService documentService;

    private static final Path ALLOWED_BASE;
    static {
        try {
            ALLOWED_BASE = Path.of(System.getProperty("java.io.tmpdir"))
                    .toRealPath()
                    .normalize();
        } catch (IOException e) {
            throw new ExceptionInInitializerError(
                    "Cannot resolve temp directory: " + e.getMessage());
        }
    }

    // ── JSON endpoints ────────────────────────────────────────────────────

    @PostMapping(value = "/analyze", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAnyRole('ANALYST', 'ADMIN')")
    public ResponseEntity<DocumentAnalysisResponse> analyzeDocument(
            @RequestBody @Valid DocumentUploadRequest request,
            @AuthenticationPrincipal User user) {

        validateFilePath(request.filePath());
        return ResponseEntity.ok(
                documentService.analyzeDocument(request, user.getId().toString())
        );
    }

    @PostMapping(value = "/upload", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAnyRole('ANALYST', 'ADMIN')")
    public ResponseEntity<KnowledgeUploadResponse> uploadDocument(
            @RequestBody @Valid DocumentUploadRequest request,
            @AuthenticationPrincipal User user) {

        validateFilePath(request.filePath());
        return ResponseEntity.ok(
                documentService.uploadToKnowledge(request, user.getId().toString())
        );
    }

    // ── Multipart endpoints ───────────────────────────────────────────────

    @PostMapping(value = "/analyze", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @PreAuthorize("hasAnyRole('ANALYST', 'ADMIN')")
    public ResponseEntity<DocumentAnalysisResponse> analyzeDocumentMultipart(
            @RequestParam("file") MultipartFile file,
            @AuthenticationPrincipal User user) {

        DocumentUploadRequest request;
        try {
            request = saveMultipartToTempRequest(file);
        } catch (IOException e) {
            throw new SentinelException("FILE_UPLOAD_ERROR", "Failed to save uploaded file temporarily", e);
        }

        try {
            return ResponseEntity.ok(
                    documentService.analyzeDocument(request, user.getId().toString())
            );
        } finally {
            cleanupTempFile(request.filePath());
        }
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @PreAuthorize("hasAnyRole('ANALYST', 'ADMIN')")
    public ResponseEntity<KnowledgeUploadResponse> uploadDocumentMultipart(
            @RequestParam("file") MultipartFile file,
            @AuthenticationPrincipal User user) {

        DocumentUploadRequest request;
        try {
            request = saveMultipartToTempRequest(file);
        } catch (IOException e) {
            throw new SentinelException("FILE_UPLOAD_ERROR", "Failed to save uploaded file temporarily", e);
        }

        try {
            return ResponseEntity.ok(
                    documentService.uploadToKnowledge(request, user.getId().toString())
            );
        } finally {
            cleanupTempFile(request.filePath());
        }
    }

    // ── Internal helpers ──────────────────────────────────────────────────

    private DocumentUploadRequest saveMultipartToTempRequest(MultipartFile file) throws IOException {
        String originalFilename = file.getOriginalFilename();
        if (originalFilename == null || originalFilename.isBlank()) {
            originalFilename = "temp_file";
        }

// Hard size limit — reject before writing to disk.
        final long MAX_SIZE_BYTES = 10L * 1024 * 1024; // 10 MB
        if (file.getSize() > MAX_SIZE_BYTES) {
            throw new SentinelException("FILE_TOO_LARGE",
                    "File exceeds the maximum allowed size of 10 MB.");
        }

// Extension whitelist — reject unsupported types before disk write.
        java.util.Set<String> ALLOWED_EXTENSIONS = java.util.Set.of("pdf", "docx", "txt", "md");
        int lastDotCheck = originalFilename.lastIndexOf('.');
        String ext = lastDotCheck != -1
                ? originalFilename.substring(lastDotCheck + 1).toLowerCase()
                : "";
        if (!ALLOWED_EXTENSIONS.contains(ext)) {
            throw new SentinelException("UNSUPPORTED_FILE_TYPE",
                    "File type '." + ext + "' is not supported. Allowed: pdf, docx, txt, md.");
        }

        String prefix = "sentinel_upload_";
        String suffix = "";
        int lastDot = originalFilename.lastIndexOf('.');
        if (lastDot != -1) {
            suffix = originalFilename.substring(lastDot);
        }

        Path tempPath = Files.createTempFile(prefix, suffix);
        file.transferTo(tempPath.toFile());

        String extension = "";
        if (lastDot != -1 && lastDot < originalFilename.length() - 1) {
            extension = originalFilename.substring(lastDot + 1);
        }

        // 5-argument constructor — userId removed from DTO (comes from auth principal)
        return new DocumentUploadRequest(
                tempPath.toAbsolutePath().toString(),
                originalFilename,
                extension,
                file.getContentType(),
                file.getSize()
        );
    }

    private void cleanupTempFile(String filePath) {
        if (filePath != null) {
            try {
                Files.deleteIfExists(Paths.get(filePath));
            } catch (IOException e) {
                log.warn("Failed to delete temporary file: {}", filePath, e);
            }
        }
    }

    private void validateFilePath(String filePath) {
        if (filePath == null || filePath.isBlank()) {
            throw new SentinelException("INVALID_FILE_PATH", "File path must not be blank.");
        }
        Path resolved = Paths.get(filePath).toAbsolutePath().normalize();
        if (!resolved.startsWith(ALLOWED_BASE)) {
            throw new ForbiddenException(
                    "File path is outside the permitted upload directory."
            );
        }
    }
}