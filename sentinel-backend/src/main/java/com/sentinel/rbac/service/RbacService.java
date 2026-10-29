package com.sentinel.rbac.service;

import com.sentinel.auth.model.Role;
import com.sentinel.rbac.model.Permission;
import com.sentinel.rbac.model.RolePermission;
import com.sentinel.rbac.repository.RolePermissionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Service;

import java.util.Set;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class RbacService {
    

    private final RolePermissionRepository rolePermissionRepository;

    @Cacheable(value = "rolePermissions", key = "#role.name()")
    public Set<Permission> getPermissionsForRole(Role role) {
        return rolePermissionRepository.findByRole(role)
                .stream()
                .map(RolePermission::getPermission)
                .collect(Collectors.toSet());
    }

    @Cacheable(value = "rolePermissions", key = "#role.name() + ':' + #permission.name()")
    public boolean hasPermission(Role role, Permission permission) {
        return rolePermissionRepository.existsByRoleAndPermission(role, permission);
    }

    public boolean hasPermission(String roleName, String permissionName) {
        try {
            Role role           = Role.valueOf(roleName.replace("ROLE_", ""));
            Permission permission = Permission.valueOf(permissionName);
            return hasPermission(role, permission);
        } catch (IllegalArgumentException ex) {
            log.warn("Unknown role or permission — denying access: role={}, permission={}",
                    roleName, permissionName);
            return false;
            // NOTE: This silent deny is intentional for security — unknown roles/permissions
            // are never granted access. If you add new enum values, update both Role and
            // Permission enums and the V2 migration script.
        }
    }
}