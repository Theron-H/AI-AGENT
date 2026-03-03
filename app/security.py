from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .db import ensure_tenant, get_env
from .models import Permission, Role, RolePermission, Tenant, User, UserRole

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = "HS256"
JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MIN", "60"))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    safe = password[:72]
    return pwd_context.hash(safe)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=JWT_EXPIRES_MIN))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def ensure_gm(db: Session) -> None:
    tenant = "default"
    if db.query(Tenant).filter(Tenant.name == tenant).first() is None:
        db.add(Tenant(name=tenant, is_active=True))
        db.commit()
    username = get_env("GM_USERNAME", "gm")
    password = get_env("GM_PASSWORD", "gm_password")

    gm = db.query(User).filter(User.tenant_id == tenant, User.username == username).first()
    if gm is None:
        gm = User(
            tenant_id=tenant,
            username=username,
            password_hash=hash_password(password),
            is_system=True,
            is_active=True,
        )
        db.add(gm)
        db.commit()

    role = db.query(Role).filter(Role.tenant_id == tenant, Role.name == "GM").first()
    if role is None:
        role = Role(tenant_id=tenant, name="GM")
        db.add(role)
        db.commit()

    link = (
        db.query(UserRole)
        .filter(UserRole.tenant_id == tenant, UserRole.user_id == gm.id, UserRole.role_id == role.id)
        .first()
    )
    if link is None:
        db.add(UserRole(tenant_id=tenant, user_id=gm.id, role_id=role.id))
        db.commit()

    default_perms = [
        "events:write",
        "events:read",
        "analytics:read",
        "reports:write",
        "reports:read",
        "tenants:manage",
        "users:manage",
        "metrics:read",
    ]
    for pname in default_perms:
        if db.query(Permission).filter(Permission.name == pname).first() is None:
            db.add(Permission(name=pname, description=pname))
            db.commit()
    for pname in default_perms:
        perm = db.query(Permission).filter(Permission.name == pname).first()
        if (
            db.query(RolePermission)
            .filter(RolePermission.tenant_id == tenant, RolePermission.role_id == role.id, RolePermission.permission_id == perm.id)
            .first()
            is None
        ):
            db.add(RolePermission(tenant_id=tenant, role_id=role.id, permission_id=perm.id))
            db.commit()


def user_roles(db: Session, tenant_id: str, user_id: int) -> list[str]:
    roles = (
        db.query(Role.name)
        .join(UserRole, Role.id == UserRole.role_id)
        .filter(Role.tenant_id == tenant_id, UserRole.user_id == user_id)
        .all()
    )
    return [r[0] for r in roles]


def user_permissions(db: Session, tenant_id: str, user_id: int) -> list[str]:
    rows = (
        db.query(Permission.name)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .filter(RolePermission.tenant_id == tenant_id, UserRole.user_id == user_id)
        .all()
    )
    return [r[0] for r in rows]


def create_user(db: Session, username: str, password: str, roles: list[str], tenant_id: str) -> User:
    tenant = ensure_tenant(tenant_id)
    user = User(tenant_id=tenant, username=username, password_hash=hash_password(password), is_active=True)
    db.add(user)
    db.commit()

    for name in roles:
        role = db.query(Role).filter(Role.tenant_id == tenant, Role.name == name).first()
        if role is None:
            role = Role(tenant_id=tenant, name=name)
            db.add(role)
            db.commit()
        db.add(UserRole(tenant_id=tenant, user_id=user.id, role_id=role.id))
    db.commit()
    return user
