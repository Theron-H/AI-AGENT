import logging
import os
import time
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from uuid import uuid4
from typing import Any

import matplotlib
import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .agent import chat_with_agent
from .analysis import (
    aggregate,
    build_echarts_bar,
    build_echarts_bar_stacked,
    build_echarts_dual_axis,
    build_echarts_line,
    build_echarts_pie,
    detect_outliers_iqr,
    detect_outliers_isolation_forest,
    summary_stats,
    trend_by_day,
)
from .db import Base, engine, ensure_tenant, get_db
from .models import (
    AuditLog,
    AnalysisTemplate,
    DataDictionary,
    EventRecord,
    Permission,
    ReportJob,
    ReportRun,
    ReportTemplate,
    Role,
    RolePermission,
    Tenant,
    User,
)
from .schemas import (
    AgentChatRequest,
    AgentChatResponse,
    EventCreate,
    LoginRequest,
    ReportJobCreate,
    TenantCreateRequest,
    TenantUpdateRequest,
    TokenResponse,
    PermissionCreateRequest,
    RolePermissionRequest,
    UserCreateRequest,
)
from .cache import cache_get, cache_set
from .emailer import send_email
from .tasks import send_report_email
from .security import (
    create_access_token,
    create_user,
    decode_token,
    ensure_gm,
    user_permissions,
    user_roles,
    verify_password,
)

app = FastAPI(title="AI Data Assistant", version="0.1.0")

matplotlib.use("Agg")
logging.basicConfig(level=logging.INFO)

REQ_COUNT = Counter("http_requests_total", "Total HTTP requests", ["path", "method", "status"])
REQ_LAT = Histogram("http_request_seconds", "HTTP request latency", ["path", "method"])

RATE_LIMITS: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_COUNT = 10


def _log(
    db: Session,
    tenant_id: str,
    action: str,
    target: str,
    detail: dict,
    user_id: int | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            action=action,
            target=target,
            detail_json=detail,
            user_id=user_id,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
    )
    db.commit()


def _req_meta(request: Request | None) -> dict[str, Any]:
    if request is None:
        return {"request_id": None, "ip": None, "user_agent": None}
    return {
        "request_id": getattr(request.state, "request_id", None),
        "ip": getattr(request.state, "ip", None),
        "user_agent": getattr(request.state, "user_agent", None),
    }


@app.on_event("startup")
def startup() -> None:
    retries = int(os.getenv("DB_INIT_MAX_RETRIES", "10"))
    delay = float(os.getenv("DB_INIT_RETRY_SECONDS", "2"))
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            db_gen = get_db()
            db = next(db_gen)
            try:
                ensure_gm(db)
            finally:
                db_gen.close()
            return
        except OperationalError as exc:
            last_exc = exc
            logging.warning("DB not ready (attempt %s/%s): %s", attempt, retries, exc)
            time.sleep(delay)
    if last_exc:
        raise last_exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
def metrics(authorization: str | None = None, db: Session = Depends(get_db)):
    user = _auth_user(db, authorization)
    _require_permission(db, user, "metrics:read")
    return StreamingResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _rate_limit(key: str) -> None:
    now = datetime.now(UTC).timestamp()
    bucket = [t for t in RATE_LIMITS.get(key, []) if now - t < RATE_LIMIT_WINDOW]
    bucket.append(now)
    RATE_LIMITS[key] = bucket
    if len(bucket) > RATE_LIMIT_COUNT:
        raise HTTPException(status_code=429, detail="Too many requests")


def _auth_user(db: Session, authorization: str | None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token") from None
    user_id = int(payload.get("sub"))
    tenant_id = payload.get("tenant_id")
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User disabled")
    tenant = db.query(Tenant).filter(Tenant.name == tenant_id).first()
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Tenant disabled")
    return user


def _require_permission(db: Session, user: User, perm: str) -> None:
    roles = user_roles(db, user.tenant_id, user.id)
    if "GM" in roles:
        return
    perms = user_permissions(db, user.tenant_id, user.id)
    if perm not in perms:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.middleware("http")
async def metrics_middleware(request, call_next):
    request.state.request_id = uuid4().hex
    request.state.ip = request.client.host if request.client else None
    request.state.user_agent = request.headers.get("user-agent")
    with REQ_LAT.labels(request.url.path, request.method).time():
        response = await call_next(request)
    REQ_COUNT.labels(request.url.path, request.method, response.status_code).inc()
    return response


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    key = f"login:{request.client.host if request.client else 'unknown'}:{req.username}"
    _rate_limit(key)
    tenant = "default"
    user = db.query(User).filter(User.tenant_id == tenant, User.username == req.username).first()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "tenant_id": tenant})
    return TokenResponse(access_token=token)


@app.post("/auth/users")
def create_user_api(
    req: UserCreateRequest,
    request: Request,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "users:manage")
    target_tenant = ensure_tenant(req.tenant_id) if req.tenant_id else user.tenant_id
    tenant = db.query(Tenant).filter(Tenant.name == target_tenant).first()
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=400, detail="Tenant not found or inactive")
    created = create_user(db, req.username, req.password, req.roles, target_tenant)
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "create_user",
        "users",
        {"target_tenant": target_tenant, "user_id": user.id, "created_id": created.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"id": created.id}


@app.post("/auth/reset-password")
def reset_password(
    request: Request,
    username: str = Query(...),
    new_password: str = Query(...),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "users:manage")
    target = db.query(User).filter(User.tenant_id == user.tenant_id, User.username == username).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    from .security import hash_password

    target.password_hash = hash_password(new_password)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "reset_password",
        "users",
        {"user_id": user.id, "target": username},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"status": "ok"}


@app.post("/tenants")
def create_tenant(
    req: TenantCreateRequest,
    request: Request,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "tenants:manage")
    if db.query(Tenant).filter(Tenant.name == req.name).first():
        raise HTTPException(status_code=400, detail="Tenant already exists")
    tenant = Tenant(name=req.name, is_active=True)
    db.add(tenant)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "create_tenant",
        "tenants",
        {"name": req.name, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"id": tenant.id}


@app.post("/permissions")
def create_permission(
    req: PermissionCreateRequest,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "users:manage")
    if db.query(Permission).filter(Permission.name == req.name).first():
        raise HTTPException(status_code=400, detail="Permission already exists")
    perm = Permission(name=req.name, description=req.description)
    db.add(perm)
    db.commit()
    return {"id": perm.id}


@app.post("/roles/{role}/permissions")
def bind_role_permissions(
    role: str,
    req: RolePermissionRequest,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "users:manage")
    role_row = db.query(Role).filter(Role.tenant_id == user.tenant_id, Role.name == role).first()
    if role_row is None:
        role_row = Role(tenant_id=user.tenant_id, name=role)
        db.add(role_row)
        db.commit()
    added = 0
    for pname in req.permissions:
        perm = db.query(Permission).filter(Permission.name == pname).first()
        if perm is None:
            perm = Permission(name=pname, description=pname)
            db.add(perm)
            db.commit()
        exists = (
            db.query(RolePermission)
            .filter(
                RolePermission.tenant_id == user.tenant_id,
                RolePermission.role_id == role_row.id,
                RolePermission.permission_id == perm.id,
            )
            .first()
        )
        if exists is None:
            db.add(RolePermission(tenant_id=user.tenant_id, role_id=role_row.id, permission_id=perm.id))
            added += 1
    db.commit()
    return {"role": role, "added": added}


@app.get("/tenants")
def list_tenants(request: Request, authorization: str | None = None, db: Session = Depends(get_db)) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "tenants:manage")
    rows = db.query(Tenant).all()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "list_tenants",
        "tenants",
        {"user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"tenants": [{"name": r.name, "is_active": r.is_active} for r in rows]}


@app.patch("/tenants/{name}")
def update_tenant(
    name: str,
    req: TenantUpdateRequest,
    request: Request,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "tenants:manage")
    tenant = db.query(Tenant).filter(Tenant.name == name).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.is_active = req.is_active
    if not req.is_active:
        db.query(User).filter(User.tenant_id == name).update({"is_active": False})
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "update_tenant",
        "tenants",
        {"name": name, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"name": tenant.name, "is_active": tenant.is_active}


@app.post("/events/batch")
def create_events(
    events: list[EventCreate],
    request: Request,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "events:write")
    tenant = user.tenant_id
    if not events:
        return {"inserted": 0}
    rows = [
        EventRecord(
            tenant_id=tenant,
            source=item.source,
            category=item.category,
            value=item.value,
            occurred_at=item.occurred_at,
            metadata_json=item.metadata,
        )
        for item in events
    ]
    db.add_all(rows)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        tenant,
        "insert_events",
        "event_records",
        {"count": len(rows), "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"inserted": len(rows)}


@app.get("/analytics/aggregate")
def aggregate_events(
    request: Request,
    group_by: str = Query(..., description="source or category"),
    metric: str = Query("value"),
    agg: str = Query("sum", description="sum, avg, count, max, min"),
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    try:
        tenant = user.tenant_id
        cache_key = f"agg:{tenant}:{group_by}:{metric}:{agg}:{start_at}:{end_at}"
        cached = cache_get(cache_key)
        if cached is not None:
            return {"data": cached, "cached": True}
        data = aggregate(
            db, tenant, group_by=group_by, metric=metric, agg=agg, start_at=start_at, end_at=end_at
        )
        cache_set(cache_key, data, ttl_seconds=60)
        meta = _req_meta(request)
        _log(
            db,
            tenant,
            "aggregate",
            "event_records",
            {"group_by": group_by, "metric": metric, "agg": agg, "user_id": user.id},
            user_id=user.id,
            request_id=meta["request_id"],
            ip=meta["ip"],
            user_agent=meta["user_agent"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"data": data}


@app.post("/agent/chat", response_model=AgentChatResponse)
def chat(
    req: AgentChatRequest,
    request: Request,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> AgentChatResponse:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    answer, data, sql = chat_with_agent(db, req.message, req.session_id, user.tenant_id)
    tenant = user.tenant_id
    meta = _req_meta(request)
    _log(
        db,
        tenant,
        "chat",
        "agent",
        {"sql": sql is not None, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return AgentChatResponse(answer=answer, data=data, sql=sql)


@app.get("/analytics/export")
def export_aggregate(
    request: Request,
    group_by: str = Query(..., description="source or category"),
    metric: str = Query("value"),
    agg: str = Query("sum", description="sum, avg, count, max, min"),
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
    format: str = Query("csv", description="csv or xlsx"),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "reports:write")
    try:
        tenant = user.tenant_id
        data = aggregate(
            db, tenant, group_by=group_by, metric=metric, agg=agg, start_at=start_at, end_at=end_at
        )
        meta = _req_meta(request)
        _log(
            db,
            tenant,
            "export",
            "event_records",
            {"group_by": group_by, "metric": metric, "agg": agg, "user_id": user.id},
            user_id=user.id,
            request_id=meta["request_id"],
            ip=meta["ip"],
            user_agent=meta["user_agent"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    df = pd.DataFrame(data)
    if format == "xlsx":
        buf = BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        headers = {"Content-Disposition": "attachment; filename=report.xlsx"}
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    if format == "csv":
        buf = StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        headers = {"Content-Disposition": "attachment; filename=report.csv"}
        return StreamingResponse(buf, media_type="text/csv", headers=headers)

    raise HTTPException(status_code=400, detail="format must be csv or xlsx")


@app.get("/analytics/chart")
def chart(
    type: str = Query("bar", description="bar, line, pie, stacked, dual"),
    metric: str = Query("value"),
    agg: str = Query("sum", description="sum, avg, count, max, min"),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    tenant = user.tenant_id
    if type == "line":
        data = trend_by_day(db, tenant)
        x = [row["day"] for row in data]
        y = [row["sum_value"] for row in data]
        option = build_echarts_line("Daily Trend", x, y, f"{agg}_{metric}")
        return {"data": data, "echarts": option}

    if type == "pie":
        data = aggregate(db, tenant, group_by="category", metric=metric, agg=agg)
        option = build_echarts_pie("Category Share", data, "category", f"{agg}_{metric}")
        return {"data": data, "echarts": option}

    if type == "stacked":
        data = aggregate(db, tenant, group_by="category", metric=metric, agg=agg)
        x = [row["category"] for row in data]
        series = [
            {
                "name": agg,
                "type": "bar",
                "stack": "total",
                "data": [row[f"{agg}_{metric}"] for row in data],
            }
        ]
        option = build_echarts_bar_stacked("Category Stacked", x, series)
        return {"data": data, "echarts": option}

    if type == "dual":
        sum_data = aggregate(db, tenant, group_by="category", metric=metric, agg="sum")
        cnt_data = aggregate(db, tenant, group_by="category", metric=metric, agg="count")
        x = [row["category"] for row in sum_data]
        y1 = [row["sum_value"] for row in sum_data]
        y2 = [row["count_value"] for row in cnt_data]
        option = build_echarts_dual_axis("Category Sum vs Count", x, y1, y2)
        return {"data": {"sum": sum_data, "count": cnt_data}, "echarts": option}

    data = aggregate(db, tenant, group_by="category", metric=metric, agg=agg)
    x = [row["category"] for row in data]
    y = [row[f"{agg}_{metric}"] for row in data]
    option = build_echarts_bar("Category Summary", x, y, f"{agg}_{metric}")
    return {"data": data, "echarts": option}


@app.get("/analytics/chart/image")
def chart_image(
    type: str = Query("bar", description="bar or line or pie"),
    metric: str = Query("value"),
    agg: str = Query("sum"),
    format: str = Query("png", description="png or svg"),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    import matplotlib.pyplot as plt

    tenant = user.tenant_id
    if type == "line":
        data = trend_by_day(db, tenant)
        x = [row["day"] for row in data]
        y = [row["sum_value"] for row in data]
        plt.figure(figsize=(8, 4))
        plt.plot(x, y, marker="o")
        plt.title("Daily Trend")
        plt.xticks(rotation=30, ha="right")
    elif type == "pie":
        data = aggregate(db, tenant, group_by="category", metric=metric, agg=agg)
        labels = [row["category"] for row in data]
        sizes = [row[f"{agg}_{metric}"] for row in data]
        plt.figure(figsize=(6, 6))
        plt.pie(sizes, labels=labels, autopct="%1.1f%%")
        plt.title("Category Share")
    else:
        data = aggregate(db, tenant, group_by="category", metric=metric, agg=agg)
        labels = [row["category"] for row in data]
        values = [row[f"{agg}_{metric}"] for row in data]
        plt.figure(figsize=(8, 4))
        plt.bar(labels, values)
        plt.title("Category Summary")
        plt.xticks(rotation=30, ha="right")

    buf = BytesIO()
    if format == "svg":
        plt.savefig(buf, format="svg", bbox_inches="tight")
        media = "image/svg+xml"
        filename = "chart.svg"
    else:
        plt.savefig(buf, format="png", bbox_inches="tight")
        media = "image/png"
        filename = "chart.png"
    plt.close()
    buf.seek(0)
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(buf, media_type=media, headers=headers)


@app.get("/analytics/summary")
def summary(
    window_days: int | None = Query(None),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    tenant = user.tenant_id
    end_at = datetime.now(UTC)
    start_at = end_at - timedelta(days=window_days) if window_days else None
    data = aggregate(
        db, tenant, group_by="category", metric="value", agg="sum", start_at=start_at, end_at=end_at
    )
    stats = summary_stats(pd.DataFrame(data).rename(columns={"sum_value": "value"}))
    return {"summary": stats}


@app.get("/analytics/outliers")
def outliers(
    window_days: int | None = Query(None),
    authorization: str | None = None,
    method: str = Query("iqr", description="iqr or isolation_forest"),
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    tenant = user.tenant_id
    end_at = datetime.now(UTC)
    start_at = end_at - timedelta(days=window_days) if window_days else None
    data = aggregate(
        db, tenant, group_by="category", metric="value", agg="sum", start_at=start_at, end_at=end_at
    )
    tmp = pd.DataFrame(data).rename(columns={"sum_value": "value"})
    if method == "isolation_forest":
        return {"outliers": detect_outliers_isolation_forest(tmp)}
    return {"outliers": detect_outliers_iqr(tmp)}


@app.get("/analytics/correlation")
def correlation(
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    tenant = user.tenant_id
    data = aggregate(db, tenant, group_by="category", metric="value", agg="sum")
    df = pd.DataFrame(data)
    if df.empty:
        return {"correlation": None}
    corr = df[f"sum_value"].corr(df.index.astype(float))
    return {"correlation": corr}


@app.post("/reports/jobs")
def create_report_job(
    req: ReportJobCreate,
    request: Request,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "reports:write")
    tenant = user.tenant_id
    job = ReportJob(
        tenant_id=tenant,
        name=req.name,
        schedule=req.schedule,
        format=req.format,
        group_by=req.group_by,
        metric=req.metric,
        agg=req.agg,
    )
    db.add(job)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        tenant,
        "create_report_job",
        "report_jobs",
        {"job_id": job.id, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"id": job.id}


@app.post("/reports/run")
def run_reports(
    request: Request,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "reports:write")
    now = datetime.now(UTC)
    jobs = db.query(ReportJob).all()
    outputs = []
    for job in jobs:
        data = aggregate(db, job.tenant_id, group_by=job.group_by, metric=job.metric, agg=job.agg)
        df = pd.DataFrame(data)
        filename = f"report_{job.id}_{now.strftime('%Y%m%d_%H%M%S')}.{job.format}"
        if job.format == "xlsx":
            df.to_excel(filename, index=False)
        else:
            df.to_csv(filename, index=False)
        job.last_run_at = now
        db.add(ReportRun(tenant_id=job.tenant_id, report_id=job.id, file_path=filename))
        outputs.append({"job_id": job.id, "file": filename})
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "run_reports",
        "report_jobs",
        {"count": len(outputs), "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    if outputs:
        subject = "Report Run Finished"
        body = "\n".join([f"{r['job_id']}: {r['file']}" for r in outputs])
        try:
            send_report_email.delay(subject, body)
        except Exception:
            send_email(subject, body)
    return {"reports": outputs}


@app.post("/events/import")
def import_events(
    request: Request,
    file: UploadFile = File(...),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "events:write")
    tenant = user.tenant_id
    if request and request.headers.get("content-length"):
        size = int(request.headers.get("content-length", "0"))
        if size > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large")
    if file.content_type not in {
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    content = file.file.read()
    if file.filename and file.filename.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(content))
    else:
        df = pd.read_csv(StringIO(content.decode("utf-8")))

    df = df.dropna(subset=["source", "category", "value", "occurred_at"]).drop_duplicates()
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], errors="coerce")
    df = df.dropna(subset=["occurred_at"])

    rows = [
        EventRecord(
            tenant_id=tenant,
            source=str(row["source"]),
            category=str(row["category"]),
            value=float(row["value"]),
            occurred_at=row["occurred_at"].to_pydatetime(),
            metadata_json={},
        )
        for _, row in df.iterrows()
    ]
    db.add_all(rows)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        tenant,
        "import_events",
        "event_records",
        {"count": len(rows), "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"inserted": len(rows)}


@app.post("/events/clean")
def clean_events(
    request: Request,
    remove_outliers: bool = Query(False),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "events:write")
    tenant = user.tenant_id
    rows = db.query(EventRecord).filter(EventRecord.tenant_id == tenant).all()
    if not rows:
        return {"cleaned": 0}
    df = pd.DataFrame(
        [{"id": r.id, "value": r.value} for r in rows],
    )
    outliers = detect_outliers_iqr(df)
    deleted = 0
    if remove_outliers and outliers:
        ids = [r["id"] for r in outliers]
        deleted = db.query(EventRecord).filter(EventRecord.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    meta = _req_meta(request)
    _log(
        db,
        tenant,
        "clean_events",
        "event_records",
        {"removed_outliers": deleted, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"removed_outliers": deleted}


@app.post("/events/simulate")
def simulate_events(
    request: Request,
    days: int = Query(7),
    per_day: int = Query(20),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "events:write")
    import random

    tenant = user.tenant_id
    categories = ["book", "food", "toy", "tech"]
    sources = ["shop", "app", "web"]
    now = datetime.now(UTC)
    rows = []
    for d in range(days):
        day = now - timedelta(days=d)
        for _ in range(per_day):
            rows.append(
                EventRecord(
                    tenant_id=tenant,
                    source=random.choice(sources),  # noqa: S311
                    category=random.choice(categories),  # noqa: S311
                    value=round(random.uniform(5, 200), 2),  # noqa: S311
                    occurred_at=day,
                    metadata_json={},
                )
            )
    db.add_all(rows)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        tenant,
        "simulate_events",
        "event_records",
        {"count": len(rows), "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"inserted": len(rows)}


@app.post("/dictionary")
def create_dictionary(
    request: Request,
    field_name: str = Query(...),
    field_type: str = Query(...),
    description: str = Query(""),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    entry = DataDictionary(
        tenant_id=user.tenant_id, field_name=field_name, field_type=field_type, description=description
    )
    db.add(entry)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "create_dictionary",
        "data_dictionary",
        {"field_name": field_name, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"id": entry.id}


@app.get("/dictionary")
def list_dictionary(authorization: str | None = None, db: Session = Depends(get_db)) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    rows = db.query(DataDictionary).filter(DataDictionary.tenant_id == user.tenant_id).all()
    _log(db, user.tenant_id, "list_dictionary", "data_dictionary", {"user_id": user.id}, user_id=user.id)
    return {
        "fields": [
            {"field_name": r.field_name, "field_type": r.field_type, "description": r.description} for r in rows
        ]
    }


@app.delete("/dictionary/{field_name}")
def delete_dictionary(field_name: str, authorization: str | None = None, db: Session = Depends(get_db)) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "events:write")
    db.query(DataDictionary).filter(
        DataDictionary.tenant_id == user.tenant_id, DataDictionary.field_name == field_name
    ).delete()
    db.commit()
    _log(
        db,
        user.tenant_id,
        "delete_dictionary",
        "data_dictionary",
        {"field_name": field_name, "user_id": user.id},
        user_id=user.id,
    )
    return {"deleted": field_name}


@app.post("/analysis/templates")
def create_analysis_template(
    request: Request,
    name: str = Query(...),
    config: dict | None = None,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    tmpl = AnalysisTemplate(tenant_id=user.tenant_id, name=name, template_json=config or {})
    db.add(tmpl)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "create_analysis_template",
        "analysis_templates",
        {"name": name, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"id": tmpl.id}


@app.get("/analysis/templates")
def list_analysis_templates(authorization: str | None = None, db: Session = Depends(get_db)) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    rows = db.query(AnalysisTemplate).filter(AnalysisTemplate.tenant_id == user.tenant_id).all()
    _log(
        db,
        user.tenant_id,
        "list_analysis_templates",
        "analysis_templates",
        {"user_id": user.id},
        user_id=user.id,
    )
    return {"templates": [{"name": r.name, "config": r.template_json} for r in rows]}


@app.post("/reports/templates")
def create_report_template(
    request: Request,
    name: str = Query(...),
    config: dict | None = None,
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "reports:write")
    tmpl = ReportTemplate(tenant_id=user.tenant_id, name=name, config_json=config or {})
    db.add(tmpl)
    db.commit()
    meta = _req_meta(request)
    _log(
        db,
        user.tenant_id,
        "create_report_template",
        "report_templates",
        {"name": name, "user_id": user.id},
        user_id=user.id,
        request_id=meta["request_id"],
        ip=meta["ip"],
        user_agent=meta["user_agent"],
    )
    return {"id": tmpl.id}


@app.get("/reports/templates")
def list_report_templates(authorization: str | None = None, db: Session = Depends(get_db)) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "reports:read")
    rows = db.query(ReportTemplate).filter(ReportTemplate.tenant_id == user.tenant_id).all()
    _log(
        db,
        user.tenant_id,
        "list_report_templates",
        "report_templates",
        {"user_id": user.id},
        user_id=user.id,
    )
    return {"templates": [{"name": r.name, "config": r.config_json} for r in rows]}


@app.get("/reports/history")
def report_history(authorization: str | None = None, db: Session = Depends(get_db)) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "reports:read")
    rows = db.query(ReportRun).filter(ReportRun.tenant_id == user.tenant_id).all()
    _log(
        db,
        user.tenant_id,
        "report_history",
        "report_runs",
        {"user_id": user.id},
        user_id=user.id,
    )
    return {"history": [{"report_id": r.report_id, "file": r.file_path} for r in rows]}


@app.get("/audit")
def audit_search(
    action: str | None = Query(None),
    target: str | None = Query(None),
    user_id: int | None = Query(None),
    request_id: str | None = Query(None),
    limit: int = Query(100),
    authorization: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = _auth_user(db, authorization)
    _require_permission(db, user, "analytics:read")
    q = db.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if target:
        q = q.filter(AuditLog.target == target)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if request_id:
        q = q.filter(AuditLog.request_id == request_id)
    rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {
        "logs": [
            {
                "action": r.action,
                "target": r.target,
                "detail": r.detail_json,
                "user_id": r.user_id,
                "request_id": r.request_id,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }
