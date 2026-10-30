package com.sentinel.admin.controller;

import com.sentinel.admin.dto.RoleChangeRequest;
import com.sentinel.admin.dto.UserSummaryResponse;
import com.sentinel.admin.service.AdminUserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/admin/users")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class AdminUserController {

    private final AdminUserService adminUserService;

    @GetMapping
    public ResponseEntity<List<UserSummaryResponse>> listUsers() {
        return ResponseEntity.ok(adminUserService.listUsers());
    }

    @PatchMapping("/{id}/role")
    public ResponseEntity<UserSummaryResponse> changeRole(
            @PathVariable UUID id,
            @Valid @RequestBody RoleChangeRequest request,
            @AuthenticationPrincipal UserDetails actor) {
        return ResponseEntity.ok(
                adminUserService.changeRole(id, request.role(), actor.getUsername()));
    }
}