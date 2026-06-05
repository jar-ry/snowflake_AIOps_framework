import streamlit as st
import altair as alt
import pandas as pd
from snowflake.snowpark.context import get_active_session

st.set_page_config(
    page_title="AI Monitoring Dashboard",
    page_icon=":material/monitoring:",
    layout="wide",
)

session = get_active_session()

# The dashboard is deployed into the eval database; derive it from the session so
# the same code works for any deployment (no hardcoded database name).
EVAL_DB = (session.get_current_database() or "").strip('"')
if not EVAL_DB:
    st.error(
        "Could not determine the eval database from the current session. "
        "Deploy this app into the eval database's MONITORING schema."
    )
    st.stop()
MON = f"{EVAL_DB}.MONITORING"
OBS = f"{EVAL_DB}.OBSERVABILITY"


def run_query(sql):
    try:
        return session.sql(sql).to_pandas()
    except Exception as e:
        return pd.DataFrame()


with st.sidebar:
    st.title(":material/monitoring: AI Monitoring")
    env_rows = run_query(f"SELECT DISTINCT environment FROM {MON}.V_WEEKLY_EXECUTIVE_SUMMARY WHERE environment IS NOT NULL ORDER BY 1")
    env_options = ["All"] + (env_rows.iloc[:, 0].astype(str).tolist() if not env_rows.empty else [])
    env_filter = st.selectbox(
        "Environment",
        env_options,
        index=0,
    )
    time_window = st.selectbox(
        "Time window",
        ["Last 1 hour", "Last 6 hours", "Last 24 hours", "Last 7 days", "Last 30 days"],
        index=2,
    )
    granularity = st.selectbox(
        "Granularity",
        ["15 min", "1 hour", "1 day"],
        index=1,
    )

time_window_map = {
    "Last 1 hour": 1, "Last 6 hours": 6, "Last 24 hours": 24,
    "Last 7 days": 168, "Last 30 days": 720,
}
hours_back = time_window_map[time_window]
days_back = max(1, hours_back // 24)

granularity_sql = {
    "15 min": "DATE_TRUNC('minute', event_time)",
    "1 hour": "DATE_TRUNC('hour', event_time)",
    "1 day": "DATE_TRUNC('day', event_time)",
}
trunc_expr = granularity_sql[granularity]

env_clause = (
    f"AND environment = '{env_filter}'" if env_filter != "All" else ""
)
time_filter = f"event_time >= DATEADD('hour', -{hours_back}, CURRENT_TIMESTAMP())"

tab_overview, tab_evals, tab_quality, tab_feedback, tab_costs, tab_alerts = st.tabs([
    ":material/dashboard: Overview",
    ":material/check_circle: Evaluations",
    ":material/flag: Interaction quality",
    ":material/chat: Feedback",
    ":material/payments: Credits",
    ":material/warning: Alerts",
])

with tab_overview:
    st.header("Executive summary")

    weekly = run_query(f"""
        SELECT week_start, environment, total_requests, success_rate_pct,
               total_tokens, total_credits, avg_latency_ms, total_user_sessions
        FROM {MON}.V_WEEKLY_EXECUTIVE_SUMMARY
        WHERE week_start >= DATEADD('day', -{days_back}, CURRENT_DATE()) {env_clause}
        ORDER BY week_start DESC
        LIMIT 52
    """)

    if not weekly.empty:
        latest = weekly.iloc[0]
        prev = weekly.iloc[1] if len(weekly) > 1 else latest

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(
                "Weekly requests",
                f"{int(latest['TOTAL_REQUESTS']):,}",
                delta=f"{int(latest['TOTAL_REQUESTS'] - prev['TOTAL_REQUESTS']):+,}" if len(weekly) > 1 else None,
            )
        with c2:
            st.metric(
                "Success rate",
                f"{latest['SUCCESS_RATE_PCT']:.1f}%",
                delta=f"{latest['SUCCESS_RATE_PCT'] - prev['SUCCESS_RATE_PCT']:+.1f}pp" if len(weekly) > 1 else None,
            )
        with c3:
            st.metric(
                "Weekly credits",
                f"{latest['TOTAL_CREDITS']:.4f}",
                delta=f"{latest['TOTAL_CREDITS'] - prev['TOTAL_CREDITS']:+.4f}" if len(weekly) > 1 else None,
                delta_color="inverse",
            )
        with c4:
            st.metric(
                "Avg latency",
                f"{latest['AVG_LATENCY_MS']:.0f}ms",
                delta=f"{latest['AVG_LATENCY_MS'] - prev['AVG_LATENCY_MS']:+.0f}ms" if len(weekly) > 1 else None,
                delta_color="inverse",
            )

        st.subheader("Weekly trends")
        weekly_sorted = weekly.sort_values("WEEK_START")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Requests & success rate**")
            base = alt.Chart(weekly_sorted).encode(
                x=alt.X("WEEK_START:T", title="Week")
            )
            bars = base.mark_bar(opacity=0.4, color="#4e79a7").encode(
                y=alt.Y("TOTAL_REQUESTS:Q", title="Requests")
            )
            line = base.mark_line(color="#e15759", strokeWidth=2).encode(
                y=alt.Y("SUCCESS_RATE_PCT:Q", title="Success %",
                        scale=alt.Scale(domain=[80, 100]))
            )
            st.altair_chart(
                alt.layer(bars, line).resolve_scale(y="independent"),
                use_container_width=True,
            )
        with col2:
            st.markdown("**Credits trend**")
            st.bar_chart(weekly_sorted, x="WEEK_START", y="TOTAL_CREDITS")
    else:
        st.info("No executive summary data available yet.")

    st.subheader("Health status")
    health = run_query(f"""
        SELECT check_name, environment, target_name, status, details,
               latency_ms, checked_at
        FROM {MON}.V_HEALTH_DASHBOARD
        ORDER BY CASE status
            WHEN 'UNHEALTHY' THEN 0 WHEN 'DEGRADED' THEN 1 ELSE 2
        END, checked_at DESC
    """)
    if not health.empty:
        h_counts = health["STATUS"].value_counts()
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Healthy", int(h_counts.get("HEALTHY", 0)))
        with c2:
            st.metric("Degraded", int(h_counts.get("DEGRADED", 0)))
        with c3:
            st.metric("Unhealthy", int(h_counts.get("UNHEALTHY", 0)))
        st.dataframe(health)
    else:
        st.info("No health check results yet. Run the health check script first.")

with tab_evals:
    st.header("Evaluation accuracy trends")

    evals = run_query(f"""
        SELECT eval_date, eval_type, environment, target_name,
               accuracy_pct, threshold_pct, passed_threshold,
               total_questions, passed_questions, accuracy_delta
        FROM {MON}.V_EVAL_ACCURACY_TREND
        WHERE eval_date >= DATEADD('day', -{days_back}, CURRENT_DATE()) {env_clause}
        ORDER BY eval_date DESC
    """)

    if not evals.empty:
        latest_evals = evals.drop_duplicates(subset=["TARGET_NAME", "EVAL_TYPE"], keep="first")
        cols = st.columns(len(latest_evals))
        for i, (_, row) in enumerate(latest_evals.iterrows()):
            with cols[i]:
                delta_str = f"{row['ACCURACY_DELTA']:+.1f}pp" if pd.notna(row["ACCURACY_DELTA"]) else None
                st.metric(
                    f"{row['TARGET_NAME']} ({row['EVAL_TYPE']})",
                    f"{row['ACCURACY_PCT']:.1f}%",
                    delta=delta_str,
                )

        st.markdown("**Accuracy over time**")
        chart = alt.Chart(evals).mark_line(point=True).encode(
            x=alt.X("EVAL_DATE:T", title="Date"),
            y=alt.Y("ACCURACY_PCT:Q", title="Accuracy %", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("TARGET_NAME:N", title="Target"),
            strokeDash="EVAL_TYPE:N",
            tooltip=["EVAL_DATE:T", "TARGET_NAME:N", "EVAL_TYPE:N",
                     "ACCURACY_PCT:Q", "THRESHOLD_PCT:Q"],
        )
        threshold = alt.Chart(evals).mark_rule(
            strokeDash=[4, 4], color="red", opacity=0.5
        ).encode(y="mean(THRESHOLD_PCT):Q")
        st.altair_chart(chart + threshold, use_container_width=True)

        st.markdown("**Evaluation history**")
        st.dataframe(evals)
    else:
        st.info("No evaluation data available yet.")

with tab_quality:
    st.header("Interaction quality engine")

    # Reads the aggregated INTERACTION_QUALITY_DAILY base table (daily flag counts
    # produced by the rules engine). Daily-bucketed regardless of granularity.
    quality_live = run_query(f"""
        SELECT
            summary_date AS time_bucket,
            total_requests,
            excessive_steps_count,
            high_token_burn_count,
            slow_request_count,
            planning_error_count,
            flagged_requests AS flagged_count
        FROM {MON}.INTERACTION_QUALITY_DAILY
        WHERE summary_date >= DATEADD('day', -{days_back}, CURRENT_DATE()) {env_clause}
        ORDER BY summary_date
    """)

    if not quality_live.empty:
        total_req = int(quality_live["TOTAL_REQUESTS"].sum())
        total_flagged = int(quality_live["FLAGGED_COUNT"].sum())
        flagged_pct = round(total_flagged * 100.0 / max(total_req, 1), 1)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total requests", f"{total_req:,}")
        with c2:
            st.metric("Flagged", f"{total_flagged} ({flagged_pct}%)")
        with c3:
            st.metric("High token burn", int(quality_live["HIGH_TOKEN_BURN_COUNT"].sum()))
        with c4:
            st.metric("Excessive steps", int(quality_live["EXCESSIVE_STEPS_COUNT"].sum()))

        st.markdown(f"**Request-level flags ({granularity})**")
        flag_cols = ["EXCESSIVE_STEPS_COUNT", "HIGH_TOKEN_BURN_COUNT",
                     "SLOW_REQUEST_COUNT", "PLANNING_ERROR_COUNT"]
        flag_labels = ["Excessive steps", "High token burn", "Slow request", "Planning error"]
        flag_data = pd.melt(
            quality_live[["TIME_BUCKET"] + flag_cols],
            id_vars=["TIME_BUCKET"],
            var_name="Flag",
            value_name="Count",
        )
        flag_data["Flag"] = flag_data["Flag"].map(dict(zip(flag_cols, flag_labels)))
        chart = alt.Chart(flag_data).mark_bar().encode(
            x=alt.X("TIME_BUCKET:T", title="Time"),
            y=alt.Y("Count:Q", title="Count"),
            color=alt.Color("Flag:N"),
            tooltip=["TIME_BUCKET:T", "Flag:N", "Count:Q"],
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No interaction quality data available yet.")

    st.subheader("Currently flagged interactions")
    flags = run_query(f"""
        SELECT severity, agent_name, user_query,
               steps, total_tokens, total_duration_ms,
               flag_tool_looping AS tool_looping,
               flag_excessive_steps AS excessive_steps,
               flag_slow_request AS slow_request,
               flag_high_token_burn AS high_token_burn,
               flag_planning_error AS planning_error,
               event_time, environment
        FROM {MON}.V_INTERACTION_QUALITY_FLAGS
        WHERE {time_filter} {env_clause}
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
                 event_time DESC
        LIMIT 100
    """)
    if not flags.empty:
        st.dataframe(flags, use_container_width=True)
    else:
        st.success("No flagged interactions in this period.")

with tab_feedback:
    st.header("User feedback trends")

    feedback = run_query(f"""
        SELECT summary_date, environment, agent_or_sv_name,
               total_feedback, positive_count, neutral_count, negative_count,
               avg_rating, negative_pct, rolling_7d_avg_rating,
               rolling_7d_negative_pct
        FROM {MON}.V_FEEDBACK_TREND
        WHERE summary_date >= DATEADD('day', -{days_back}, CURRENT_DATE()) {env_clause}
        ORDER BY summary_date DESC
    """)

    if not feedback.empty:
        latest_fb = feedback.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Avg rating", f"{latest_fb['AVG_RATING']:.2f}/5")
        with c2:
            st.metric(
                "7d avg rating",
                f"{latest_fb['ROLLING_7D_AVG_RATING']:.2f}/5" if pd.notna(latest_fb.get("ROLLING_7D_AVG_RATING")) else "N/A",
            )
        with c3:
            st.metric("Negative %", f"{latest_fb['NEGATIVE_PCT']:.1f}%")
        with c4:
            st.metric("Total feedback", int(latest_fb["TOTAL_FEEDBACK"]))

        st.markdown("**Sentiment distribution**")
        fb_sorted = feedback.sort_values("SUMMARY_DATE")
        sentiment_data = pd.melt(
            fb_sorted[["SUMMARY_DATE", "POSITIVE_COUNT", "NEUTRAL_COUNT", "NEGATIVE_COUNT"]],
            id_vars=["SUMMARY_DATE"],
            var_name="Sentiment",
            value_name="Count",
        )
        sentiment_data["Sentiment"] = sentiment_data["Sentiment"].map({
            "POSITIVE_COUNT": "Positive",
            "NEUTRAL_COUNT": "Neutral",
            "NEGATIVE_COUNT": "Negative",
        })
        chart = alt.Chart(sentiment_data).mark_bar().encode(
            x=alt.X("SUMMARY_DATE:T", title="Date"),
            y=alt.Y("Count:Q", stack=True),
            color=alt.Color("Sentiment:N", scale=alt.Scale(
                domain=["Positive", "Neutral", "Negative"],
                range=["#59a14f", "#bab0ac", "#e15759"]
            )),
            tooltip=["SUMMARY_DATE:T", "Sentiment:N", "Count:Q"],
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No feedback data available yet.")

with tab_costs:
    st.header("Token usage & credits")
    st.caption(
        "Credits are cache-aware **estimates** (cache-read input billed at the cheaper cache rate; "
        "rates from config/defaults.yaml). For ground-truth spend, reconcile against ACCOUNT_USAGE "
        "metering (see monitoring/cost_reconcile.py)."
    )

    # Reads the aggregated USAGE_METRICS base table (cache-aware estimated_credits
    # is precomputed at write time). USAGE_METRICS is daily, so this tab is always
    # day-bucketed regardless of the granularity selector.
    costs = run_query(f"""
        SELECT metric_date AS time_bucket,
               environment,
               service_type,
               agent_or_sv_name AS agent_name,
               total_requests,
               total_input_tokens,
               total_output_tokens,
               total_tokens,
               total_cache_read_tokens,
               estimated_credits,
               avg_latency_ms
        FROM {MON}.USAGE_METRICS
        WHERE metric_date >= DATEADD('day', -{days_back}, CURRENT_DATE()) {env_clause}
        ORDER BY metric_date DESC
    """)

    if not costs.empty:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total credits", f"{costs['ESTIMATED_CREDITS'].sum():,.4f}")
        with c2:
            st.metric("Total tokens", f"{costs['TOTAL_TOKENS'].sum():,.0f}")
        with c3:
            st.metric("Total requests", f"{costs['TOTAL_REQUESTS'].sum():,.0f}")
        with c4:
            st.metric("Avg latency", f"{costs['AVG_LATENCY_MS'].mean():,.0f}ms")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Credits by service ({granularity})**")
            chart = alt.Chart(costs.sort_values("TIME_BUCKET")).mark_bar().encode(
                x=alt.X("TIME_BUCKET:T", title="Time"),
                y=alt.Y("sum(ESTIMATED_CREDITS):Q", title="Credits"),
                color="SERVICE_TYPE:N",
                tooltip=["TIME_BUCKET:T", "SERVICE_TYPE:N", "sum(ESTIMATED_CREDITS):Q"],
            )
            st.altair_chart(chart, use_container_width=True)

        with col2:
            st.markdown(f"**Tokens by service ({granularity})**")
            chart = alt.Chart(costs.sort_values("TIME_BUCKET")).mark_area(opacity=0.6).encode(
                x=alt.X("TIME_BUCKET:T", title="Time"),
                y=alt.Y("sum(TOTAL_TOKENS):Q", title="Tokens", stack=True),
                color="SERVICE_TYPE:N",
                tooltip=["TIME_BUCKET:T", "SERVICE_TYPE:N", "sum(TOTAL_TOKENS):Q"],
            )
            st.altair_chart(chart, use_container_width=True)

        st.markdown(f"**Latency trend ({granularity})**")
        latency_data = costs.groupby(["TIME_BUCKET", "SERVICE_TYPE"]).agg(
            {"AVG_LATENCY_MS": "mean"}
        ).reset_index()
        chart = alt.Chart(latency_data).mark_line(point=True).encode(
            x=alt.X("TIME_BUCKET:T", title="Time"),
            y=alt.Y("AVG_LATENCY_MS:Q", title="Avg Latency (ms)"),
            color="SERVICE_TYPE:N",
            tooltip=["TIME_BUCKET:T", "SERVICE_TYPE:N", "AVG_LATENCY_MS:Q"],
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No token credit data available yet.")

with tab_alerts:
    st.header("Alerts & health")

    # --- Health check failures (top priority) ---
    health_failures = run_query(f"""
        SELECT check_name, environment, target_name, status, details, checked_at
        FROM {MON}.HEALTH_CHECK_RESULTS
        WHERE status IN ('UNHEALTHY', 'DEGRADED')
          AND checked_at >= DATEADD('day', -{days_back}, CURRENT_TIMESTAMP()) {env_clause}
        ORDER BY CASE status WHEN 'UNHEALTHY' THEN 0 ELSE 1 END, checked_at DESC
        LIMIT 50
    """)

    if not health_failures.empty:
        unhealthy_count = len(health_failures[health_failures["STATUS"] == "UNHEALTHY"])
        degraded_count = len(health_failures[health_failures["STATUS"] == "DEGRADED"])
        with st.expander(f"🏥 Health check failures ({unhealthy_count} unhealthy, {degraded_count} degraded)", expanded=True):
            for _, row in health_failures.iterrows():
                icon = "🔴" if row["STATUS"] == "UNHEALTHY" else "🟠"
                st.markdown(f"{icon} **{row['CHECK_NAME']}** — `{row['TARGET_NAME']}`")
                st.caption(f"{row['DETAILS']} | {row['CHECKED_AT']}")
    else:
        st.success("All health checks passing.")

    st.divider()

    # --- Alert timeseries ---
    st.subheader("Alert trend")
    alert_trend = run_query(f"""
        SELECT DATE_TRUNC('day', created_at)::DATE AS alert_date,
               severity,
               COUNT(*) AS alert_count
        FROM {MON}.ALERT_HISTORY
        WHERE created_at >= DATEADD('day', -{days_back}, CURRENT_TIMESTAMP()) {env_clause}
        GROUP BY 1, 2
        ORDER BY 1
    """)

    if not alert_trend.empty:
        chart = alt.Chart(alert_trend).mark_bar().encode(
            x=alt.X("ALERT_DATE:T", title="Date"),
            y=alt.Y("ALERT_COUNT:Q", title="Alerts"),
            color=alt.Color("SEVERITY:N", scale=alt.Scale(
                domain=["CRITICAL", "WARNING", "INFO"],
                range=["#FF4B4B", "#FFA500", "#4B9CD3"]
            )),
            tooltip=["ALERT_DATE:T", "SEVERITY:N", "ALERT_COUNT:Q"],
        ).properties(height=200)
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No alerts in this period.")

    st.divider()

    # --- Active alerts with filtering ---
    st.subheader("Active alerts")

    active_alerts = run_query(f"""
        SELECT alert_id, alert_type, severity, environment, target_name,
               message, metric_value, threshold_value,
               created_at, hours_since_created
        FROM {MON}.V_ACTIVE_ALERTS
        WHERE 1=1 {env_clause}
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
                 created_at DESC
    """)

    if not active_alerts.empty:
        # Filters
        col_sev, col_type = st.columns(2)
        with col_sev:
            sev_options = ["All"] + sorted(active_alerts["SEVERITY"].unique().tolist())
            sev_filter = st.selectbox("Severity", sev_options, key="alert_sev_filter")
        with col_type:
            type_options = ["All"] + sorted(active_alerts["ALERT_TYPE"].unique().tolist())
            type_filter = st.selectbox("Alert type", type_options, key="alert_type_filter")

        filtered = active_alerts.copy()
        if sev_filter != "All":
            filtered = filtered[filtered["SEVERITY"] == sev_filter]
        if type_filter != "All":
            filtered = filtered[filtered["ALERT_TYPE"] == type_filter]

        # KPI row
        c1, c2, c3 = st.columns(3)
        crit = len(filtered[filtered["SEVERITY"] == "CRITICAL"])
        warn = len(filtered[filtered["SEVERITY"] == "WARNING"])
        with c1:
            st.metric("Critical", crit)
        with c2:
            st.metric("Warning", warn)
        with c3:
            st.metric("Showing", len(filtered))

        # Collapsible alert cards
        for _, alert in filtered.iterrows():
            severity = alert["SEVERITY"]
            icon = "🔴" if severity == "CRITICAL" else "🟡"
            with st.expander(f"{icon} [{severity}] {alert['ALERT_TYPE']} — {alert['TARGET_NAME']}", expanded=False):
                st.write(alert["MESSAGE"])
                st.caption(
                    f"Metric: {alert['METRIC_VALUE']} | Threshold: {alert['THRESHOLD_VALUE']} | "
                    f"Created: {alert['CREATED_AT']} ({int(alert['HOURS_SINCE_CREATED'])}h ago)"
                )
    else:
        st.success("No active alerts.")

    st.divider()

    # --- Alert history (collapsible) ---
    with st.expander("Alert history (full table)", expanded=False):
        alert_history = run_query(f"""
            SELECT alert_type, severity, environment, target_name,
                   message, metric_value, threshold_value,
                   acknowledged, created_at
            FROM {MON}.ALERT_HISTORY
            WHERE created_at >= DATEADD('day', -{days_back}, CURRENT_TIMESTAMP()) {env_clause}
            ORDER BY created_at DESC
            LIMIT 200
        """)
        if not alert_history.empty:
            st.dataframe(alert_history, use_container_width=True)
        else:
            st.caption("No alerts in this period.")

st.caption("Data refreshes every 10 minutes. Powered by the monitoring schema.")
