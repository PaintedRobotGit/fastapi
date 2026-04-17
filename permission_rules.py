"""Rules for which roles may edit role_permissions and which permission keys they may assign."""

from __future__ import annotations

from models import Permission, Role

# Higher number = higher authority within the same tier.
_ROLE_RANK: dict[str, int] = {
    "super_admin": 400,
    "admin": 300,
    "partner_owner": 220,
    "partner_admin": 210,
    "partner_member": 160,
    "customer_owner": 220,
    "customer_admin": 210,
    "customer_member": 160,
}


def role_rank(name: str) -> int:
    return _ROLE_RANK.get(name, 0)


def permission_key_scope(key: str) -> str:
    """Classify permission keys: admin (global), partner-scoped, or customer-scoped."""
    if key.startswith("partner_") or key.startswith("partner:"):
        return "partner"
    if key.startswith("customer_") or key.startswith("customer:"):
        return "customer"
    return "admin"


def can_assign_permission_key(
    *,
    is_admin: bool,
    caller_tier: str,
    permission_key: str,
) -> bool:
    if is_admin:
        return True
    scope = permission_key_scope(permission_key)
    if caller_tier == "partner":
        return scope in ("partner", "customer")
    if caller_tier == "customer":
        return scope == "customer"
    return False


def can_manage_role_permissions(
    *,
    is_admin: bool,
    caller_tier: str,
    caller_role_name: str,
    target_role: Role,
) -> bool:
    """Whether the caller may attach/detach permissions on target_role."""
    if is_admin:
        if target_role.tier != "admin":
            return True
        if caller_role_name == "super_admin":
            return True
        if target_role.name == "super_admin":
            return False
        return role_rank(caller_role_name) > role_rank(target_role.name)

    if target_role.tier == "admin":
        return False

    if caller_tier == "partner":
        if target_role.tier == "customer":
            return True
        if target_role.tier == "partner":
            return role_rank(caller_role_name) > role_rank(target_role.name)
        return False

    if caller_tier == "customer":
        if target_role.tier != "customer":
            return False
        return role_rank(caller_role_name) > role_rank(target_role.name)

    return False


def can_view_role(
    *,
    is_admin: bool,
    caller_tier: str,
    target_role: Role,
) -> bool:
    """Whether the caller may read role details and its permission list."""
    if is_admin:
        return True
    if caller_tier == "partner":
        return target_role.tier in ("partner", "customer")
    if caller_tier == "customer":
        return target_role.tier == "customer"
    return False


def permission_filter_for_caller(*, is_admin: bool, caller_tier: str):
    """SQLAlchemy boolean expression for permissions visible to list/get."""
    from sqlalchemy import false, or_

    if is_admin:
        return None
    if caller_tier == "partner":
        return or_(
            Permission.key.startswith("partner_"),
            Permission.key.startswith("partner:"),
            Permission.key.startswith("customer_"),
            Permission.key.startswith("customer:"),
        )
    if caller_tier == "customer":
        return or_(
            Permission.key.startswith("customer_"),
            Permission.key.startswith("customer:"),
        )
    return false()
