from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

ALLOWED_GROUP_FIELDS = {"source", "category"}
ALLOWED_AGGS = {"sum", "avg", "count", "max", "min"}
FORBIDDEN_SQL_TOKENS = {"insert", "update", "delete", "drop", "alter", "create", "pragma", ";", "--"}


def read_events_df(
    db: Session,
    tenant_id: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> pd.DataFrame:
    sql = "SELECT id, source, category, value, occurred_at FROM event_records WHERE tenant_id = :tenant_id"
    params: dict[str, object] = {}
    params["tenant_id"] = tenant_id

    if start_at is not None:
        sql += " AND occurred_at >= :start_at"
        params["start_at"] = start_at
    if end_at is not None:
        sql += " AND occurred_at <= :end_at"
        params["end_at"] = end_at

    rows = db.execute(text(sql), params).mappings().all()
    if not rows:
        return pd.DataFrame(columns=["id", "source", "category", "value", "occurred_at"])

    df = pd.DataFrame(rows)
    df["occurred_at"] = pd.to_datetime(df["occurred_at"])
    return df


def aggregate(
    db: Session,
    tenant_id: str,
    group_by: str,
    metric: str = "value",
    agg: str = "sum",
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict]:
    if group_by not in ALLOWED_GROUP_FIELDS:
        raise ValueError(f"group_by must be one of {sorted(ALLOWED_GROUP_FIELDS)}")
    if agg not in ALLOWED_AGGS:
        raise ValueError(f"agg must be one of {sorted(ALLOWED_AGGS)}")
    if metric != "value":
        raise ValueError("Only metric=value is currently supported")

    df = read_events_df(db, tenant_id, start_at, end_at)
    if df.empty:
        return []

    grouped = df.groupby(group_by)[metric]
    if agg == "sum":
        out = grouped.sum()
    elif agg == "avg":
        out = grouped.mean()
    elif agg == "count":
        out = grouped.count()
    elif agg == "max":
        out = grouped.max()
    else:
        out = grouped.min()

    result_df = out.reset_index().rename(columns={metric: f"{agg}_{metric}"})
    return result_df.to_dict(orient="records")


def trend_by_day(db: Session, tenant_id: str) -> list[dict]:
    df = read_events_df(db, tenant_id)
    if df.empty:
        return []

    df["day"] = df["occurred_at"].dt.date.astype(str)
    trend = df.groupby("day")["value"].sum().reset_index().rename(columns={"value": "sum_value"})
    return trend.to_dict(orient="records")


def top_categories(db: Session, tenant_id: str, n: int = 3) -> list[dict]:
    df = read_events_df(db, tenant_id)
    if df.empty:
        return []

    out = df.groupby("category")["value"].sum().reset_index().rename(columns={"value": "sum_value"})
    out = out.sort_values("sum_value", ascending=False).head(n)
    return out.to_dict(orient="records")


def run_readonly_sql(db: Session, tenant_id: str, query: str) -> list[dict]:
    q = query.strip().lower()
    if not q.startswith("select"):
        raise ValueError("Only SELECT queries are allowed")
    if "from event_records" not in q:
        raise ValueError("Only event_records table is allowed")
    for token in FORBIDDEN_SQL_TOKENS:
        if token in q:
            raise ValueError("Query contains forbidden tokens")

    if "where" in q:
        query = f"{query} AND tenant_id = :tenant_id"
    else:
        query = f"{query} WHERE tenant_id = :tenant_id"

    rows = db.execute(text(query), {"tenant_id": tenant_id}).mappings().all()
    return [dict(row) for row in rows]


def build_echarts_bar(title: str, x: list[str], y: list[float], y_name: str) -> dict:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": x},
        "yAxis": {"type": "value", "name": y_name},
        "series": [{"type": "bar", "data": y}],
    }


def build_echarts_line(title: str, x: list[str], y: list[float], y_name: str) -> dict:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": x},
        "yAxis": {"type": "value", "name": y_name},
        "series": [{"type": "line", "data": y, "smooth": True}],
    }


def build_echarts_pie(title: str, data: list[dict], name_field: str, value_field: str) -> dict:
    series_data = [{"name": row[name_field], "value": row[value_field]} for row in data]
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item"},
        "legend": {"orient": "vertical", "left": "left"},
        "series": [{"type": "pie", "radius": "50%", "data": series_data}],
    }


def build_echarts_bar_stacked(title: str, x: list[str], series: list[dict]) -> dict:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "legend": {},
        "xAxis": {"type": "category", "data": x},
        "yAxis": {"type": "value"},
        "series": series,
    }


def build_echarts_dual_axis(title: str, x: list[str], y1: list[float], y2: list[float]) -> dict:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["sum_value", "count"]},
        "xAxis": {"type": "category", "data": x},
        "yAxis": [{"type": "value", "name": "sum_value"}, {"type": "value", "name": "count"}],
        "series": [
            {"type": "bar", "data": y1, "yAxisIndex": 0},
            {"type": "line", "data": y2, "yAxisIndex": 1, "smooth": True},
        ],
    }


def summary_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    desc = df["value"].describe(percentiles=[0.25, 0.5, 0.75]).to_dict()
    return {
        "count": float(desc.get("count", 0)),
        "mean": float(desc.get("mean", 0)),
        "std": float(desc.get("std", 0)),
        "min": float(desc.get("min", 0)),
        "p25": float(desc.get("25%", 0)),
        "p50": float(desc.get("50%", 0)),
        "p75": float(desc.get("75%", 0)),
        "max": float(desc.get("max", 0)),
    }


def detect_outliers_iqr(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    q1 = df["value"].quantile(0.25)
    q3 = df["value"].quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return []
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    out = df[(df["value"] < lower) | (df["value"] > upper)]
    return out.to_dict(orient="records")


def detect_outliers_isolation_forest(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    try:
        from sklearn.ensemble import IsolationForest
    except Exception:
        return []
    model = IsolationForest(contamination=0.05, random_state=42)
    preds = model.fit_predict(df[["value"]])
    out = df[preds == -1]
    return out.to_dict(orient="records")
