from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from .analysis import aggregate, run_readonly_sql, top_categories, trend_by_day
from .db import ensure_tenant
from .models import ChatMessage

load_dotenv()


def _rule_router(message: str) -> tuple[str, list[dict[str, Any]]]:
    text = message.lower()
    if any(token in text for token in ["趋势", "trend", "daily", "按天"]):
        return "trend_by_day", []
    if any(token in text for token in ["top", "最高", "最多", "排行"]):
        return "top_categories", []
    if any(token in text for token in ["平均", "avg", "mean"]):
        return "aggregate_avg_category", []
    if any(token in text for token in ["数量", "count", "条数"]):
        return "aggregate_count_category", []
    if text.startswith("sql:"):
        return "run_sql", []
    return "aggregate_sum_category", []


def _maybe_openai_intent(message: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=api_key)
    prompt = (
        "You are an intent classifier. Output exactly one token:\n"
        "- trend_by_day\n"
        "- top_categories\n"
        "- aggregate_sum_category\n"
        "- aggregate_avg_category\n"
        "- aggregate_count_category\n"
        "User message:\n"
        f"{message}"
    )
    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        intent = (resp.output_text or "").strip()
        if intent in {
            "trend_by_day",
            "top_categories",
            "aggregate_sum_category",
            "aggregate_avg_category",
            "aggregate_count_category",
        }:
            return intent
    except Exception:
        return None
    return None


def _maybe_openai_sql(message: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    schema = (
        "Table: event_records\n"
        "Columns:\n"
        "- id (int)\n"
        "- source (text)\n"
        "- category (text)\n"
        "- value (float)\n"
        "- occurred_at (datetime)\n"
    )
    prompt = (
        "Convert user request to a safe SQLite SELECT query only. "
        "Use only the event_records table and listed columns. "
        "Return SQL only, no markdown or commentary. Avoid functions not in SQLite.\n"
        f"{schema}\nUser request:\n{message}"
    )
    try:
        client = OpenAI(api_key=api_key)
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        sql = (resp.output_text or "").strip()
        if sql.lower().startswith("select"):
            return sql
    except Exception:
        return None
    return None


def _validate_sql(sql: str) -> bool:
    q = sql.strip().lower()
    if not q.startswith("select"):
        return False
    if "from event_records" not in q:
        return False
    for token in ["insert", "update", "delete", "drop", "alter", "create", "pragma", ";", "--"]:
        if token in q:
            return False
    return True


def _save_message(db: Session, tenant_id: str, session_id: str, role: str, content: str) -> None:
    db.add(ChatMessage(tenant_id=tenant_id, session_id=session_id, role=role, content=content))
    db.commit()


def _load_recent_messages(
    db: Session, tenant_id: str, session_id: str, limit: int = 10
) -> list[dict[str, str]]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.tenant_id == tenant_id, ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    return [{"role": r.role, "content": r.content} for r in rows]


def chat_with_agent(
    db: Session,
    message: str,
    session_id: str,
    tenant_id: str | None,
) -> tuple[str, list[dict[str, Any]], str | None]:
    tenant = ensure_tenant(tenant_id)
    _save_message(db, tenant, session_id, "user", message)
    intent = _maybe_openai_intent(message)
    if intent is None:
        intent, _ = _rule_router(message)

    if intent == "trend_by_day":
        data = trend_by_day(db, tenant)
        return "这是按天汇总的金额趋势。", data, None
    if intent == "top_categories":
        data = top_categories(db, tenant, n=3)
        return "这是金额最高的 Top 3 类别。", data, None
    if intent == "aggregate_avg_category":
        data = aggregate(db, tenant, group_by="category", metric="value", agg="avg")
        return "这是各类别的平均金额。", data, None
    if intent == "aggregate_count_category":
        data = aggregate(db, tenant, group_by="category", metric="value", agg="count")
        answer = "这是各类别的数据条数。"
        _save_message(db, tenant, session_id, "assistant", answer)
        return answer, data, None
    if intent == "run_sql":
        sql = message[4:].strip()
        data = run_readonly_sql(db, tenant, sql)
        answer = "已执行只读 SQL 查询。"
        _save_message(db, tenant, session_id, "assistant", answer)
        return answer, data, sql

    sql = _maybe_openai_sql(message)
    if sql:
        if _validate_sql(sql):
            try:
                data = run_readonly_sql(db, tenant, sql)
                answer = "已将自然语言转换为 SQL 并执行。"
                _save_message(db, tenant, session_id, "assistant", answer)
                return answer, data, sql
            except Exception as exc:
                logging.exception("NL2SQL execution failed: %s", exc)

    data = aggregate(db, tenant, group_by="category", metric="value", agg="sum")
    answer = "这是各类别的总金额。"
    _save_message(db, tenant, session_id, "assistant", answer)
    return answer, data, None
