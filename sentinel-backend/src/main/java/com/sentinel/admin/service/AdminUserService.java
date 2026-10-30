package com.sentinel.admin.service;

import com.sentinel.admin.dto.UserSummaryResponse;
import com.sentinel.auth.model.Role;
import com.sentinel.auth.model.User;
import com.sentinel.auth.repository.UserRepository;
import com.sentinel.exception.ResourceNotFoundException;
import com.sentinel.exception.RoleChangeException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class AdminUserService {

    private final UserRepository userRepository;

    @Transactional(readOnly = true)
    public List<UserSummaryResponse> listUsers() {
        return userRepository.findAll(Sort.by("username")).stream()
                .map(UserSummaryResponse::from)
                .toList();
    }

    @Transactional
    public UserSummaryResponse changeRole(UUID targetId, Role newRole, String actorUsername) {
        // Lock every active ADMIN row FIRST. A concurrent demotion blocks here until we commit,
        // then sees the committed state, so two simultaneous demotions cannot both pass the check.
        List<User> activeAdmins = userRepository.findActiveByRoleForUpdate(Role.ADMIN);

        User target = userRepository.findById(targetId)
                .orElseThrow(() -> new ResourceNotFoundException("User", targetId));

        if (target.getUsername().equals(actorUsername)) {
            throw new RoleChangeException(RoleChangeException.SELF_ROLE_CHANGE,
                    "You cannot change your own role");
        }

        Role oldRole = target.getRole();
        if (oldRole == newRole) {
            return UserSummaryResponse.from(target); // no-op, 200
        }

        if (oldRole == Role.ADMIN && target.isActive()) {
            long otherActiveAdmins = activeAdmins.stream()
                    .filter(a -> !a.getId().equals(target.getId()))
                    .count();
            if (otherActiveAdmins == 0) {
                throw new RoleChangeException(RoleChangeException.LAST_ADMIN,
                        "Cannot demote the last remaining admin");
            }
        }

        target.setRole(newRole); // managed entity, flushed on commit
        log.info("Role change: actor={} target={} {} -> {}",
                actorUsername, target.getUsername(), oldRole, newRole);
        return UserSummaryResponse.from(target);
    }
}