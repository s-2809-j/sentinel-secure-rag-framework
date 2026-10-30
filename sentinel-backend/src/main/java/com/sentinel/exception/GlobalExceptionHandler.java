package com.sentinel.exception;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    // ── Validation errors ────────────────────────────────────────────────
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {
        Map<String, String> fieldErrors = new HashMap<>();
        ex.getBindingResult().getAllErrors().forEach(error -> {
            String field = ((FieldError) error).getField();
            fieldErrors.put(field, error.getDefaultMessage());
        });
        ErrorResponse body = new ErrorResponse(
                "VALIDATION_ERROR", "Request validation failed",
                HttpStatus.BAD_REQUEST.value(), fieldErrors
        );
        return ResponseEntity.badRequest().body(body);
    }

    // ── Auth errors ──────────────────────────────────────────────────────
    @ExceptionHandler(UnauthorizedException.class)
    public ResponseEntity<ErrorResponse> handleUnauthorized(UnauthorizedException ex) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(new ErrorResponse(ex.getErrorCode(), ex.getMessage(),
                        HttpStatus.UNAUTHORIZED.value(), null));
    }

    @ExceptionHandler(BadCredentialsException.class)
    public ResponseEntity<ErrorResponse> handleBadCredentials(BadCredentialsException ex) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(new ErrorResponse("INVALID_CREDENTIALS", "Invalid username or password",
                        HttpStatus.UNAUTHORIZED.value(), null));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ErrorResponse> handleAccessDenied(AccessDeniedException ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(new ErrorResponse("FORBIDDEN", "Access denied",
                        HttpStatus.FORBIDDEN.value(), null));
    }

    @ExceptionHandler(ForbiddenException.class)
    public ResponseEntity<ErrorResponse> handleForbidden(ForbiddenException ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(new ErrorResponse(ex.getErrorCode(), ex.getMessage(),
                        HttpStatus.FORBIDDEN.value(), null));
    }

    // ── Not found ────────────────────────────────────────────────────────
    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(ResourceNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ErrorResponse(ex.getErrorCode(), ex.getMessage(),
                        HttpStatus.NOT_FOUND.value(), null));
    }

    // ── FastAPI bridge errors ────────────────────────────────────────────
    @ExceptionHandler(com.sentinel.fastapi.exception.FastApiException.class)
    public ResponseEntity<ErrorResponse> handleFastApi(
            com.sentinel.fastapi.exception.FastApiException ex) {
        log.error("FastAPI communication error: {}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(new ErrorResponse("FASTAPI_ERROR",
                        "AI service is temporarily unavailable. Please try again.",
                        HttpStatus.BAD_GATEWAY.value(), null));
    }
    @ExceptionHandler(RoleChangeException.class)
    public ResponseEntity<ErrorResponse> handleRoleChange(RoleChangeException ex) {
        HttpStatus status = RoleChangeException.SELF_ROLE_CHANGE.equals(ex.getErrorCode())
                ? HttpStatus.FORBIDDEN
                : HttpStatus.CONFLICT;
        return ResponseEntity.status(status)
                .body(new ErrorResponse(ex.getErrorCode(), ex.getMessage(), status.value(), null));
    }

    // Malformed path variable (e.g. a non-UUID id) would otherwise hit the 500 catch-all
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ErrorResponse> handleTypeMismatch(MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.badRequest()
                .body(new ErrorResponse("INVALID_REQUEST", "Invalid value for parameter: " + ex.getName(),
                        HttpStatus.BAD_REQUEST.value(), null));
    }
    // ── Sentinel domain errors ───────────────────────────────────────────
    @ExceptionHandler(SentinelException.class)
    public ResponseEntity<ErrorResponse> handleSentinel(SentinelException ex) {
        log.error("Sentinel error [{}]: {}", ex.getErrorCode(), ex.getMessage());
        if ("USERNAME_CONFLICT".equals(ex.getErrorCode())) {
            return ResponseEntity.status(HttpStatus.CONFLICT)
                    .body(new ErrorResponse(ex.getErrorCode(), ex.getMessage(),
                            HttpStatus.CONFLICT.value(), null));
        }
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorResponse("INTERNAL_ERROR",
                        "An unexpected error occurred.",
                        HttpStatus.INTERNAL_SERVER_ERROR.value(), null));
    }
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleMissingRequestBody(
            HttpMessageNotReadableException ex) {

        return ResponseEntity.badRequest()
                .body(new ErrorResponse(
                        "INVALID_REQUEST",
                        "Request body is missing or malformed",
                        HttpStatus.BAD_REQUEST.value(),
                        null
                ));
    }
    // ── Catch-all ────────────────────────────────────────────────────────
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneric(Exception ex) {
        log.error("Unhandled exception", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorResponse("INTERNAL_ERROR", "An unexpected error occurred",
                        HttpStatus.INTERNAL_SERVER_ERROR.value(), null));
    }

    // ── Inner record for response body ───────────────────────────────────
    public record ErrorResponse(
            String errorCode,
            String message,
            int status,
            Map<String, String> fieldErrors,
            Instant timestamp
    ) {
        public ErrorResponse(String errorCode, String message,
                             int status, Map<String, String> fieldErrors) {
            this(errorCode, message, status, fieldErrors, Instant.now());
        }
    }
}