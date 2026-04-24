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


def run_query(sql):
    try:
        return session.sql(sql).to_pandas()
    except Exception as e:
        return pd.DataFrame()


with st.sidebar:
    st.title(":material/monitoring: AI Monitoring")
    env_filter = st.selectbox(
        "Environment",
        ["All", "RETAIL_AI_PROD", "RETAIL_AI_DEV"],
        index=0,
    )
    days_back = st.slider("Days back", 7, 90, 30)
    st.caption(f"Showing last {days_back} days")

env_clause = (
    f"AND environment = '{env_filter}'" if env_filter != "All" else ""
)

tab_overview, tab_evals, tab_quality, tab_feedback, tab_costs, tab_alerts = st.tabs([
    ":material/dashboard: Overview",
    ":material/check_circle: Evaluations",
    ":material/flag: Interaction quality",
    ":material/chat: Feedback",
    ":material/payments: Token costs",
    ":material/warning: Alerts",
])

with tab_overview:
    st.header("Executive summary")

    weekly = run_query(f"""
        SELECT week_start, environment, total_requests, success_rate_pct,
               total_tokens, total_cost_usd, avg_latency_ms, total_user_sessions
        FROM RETAIL_AI_EVAL.MONITORING.V_WEEKLY_EXECUTIVE_SUMMARY
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
                "Weekly cost",
                f"${latest['TOTAL_COST_USD']:.2f}",
                delta=f"${latest['TOTAL_COST_USD'] - prev['TOTAL_COST_USD']:+.2f}" if len(weekly) > 1 else None,
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
            st.markdown("**Cost trend**")
            st.bar_chart(weekly_sorted, x="WEEK_START", y="TOTAL_COST_USD",
                         y_label="Cost (USD)")
    else:
        st.info("No executive summary data available yet.")

    st.subheader("Health status")
    health = run_query("""
        SELECT check_name, environment, target_name, status, details,
               latency_ms, checked_at
        FROM RETAIL_AI_EVAL.MONITORING.V_HEALTH_DASHBOARD
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
        st.dataframe(health, hide_index=True)
    else:
        st.info("No health check results yet. Run the health check script first.")

with tab_evals:
    st.header("Evaluation accuracy trends")

    evals = run_query(f"""
        SELECT eval_date, eval_type, environment, target_name,
               accuracy_pct, threshold_pct, passed_threshold,
               total_questions, passed_questions, accuracy_delta
        FROM RETAIL_AI_EVAL.MONITORING.V_EVAL_ACCURACY_TREND
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
        st.dataframe(evals, hide_index=True)
    else:
        st.info("No evaluation data available yet.")

with tab_quality:
    st.header("Interaction quality engine")

    quality_daily = run_query(f"""
        SELECT *
        FROM RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_DASHBOARD
        WHERE summary_date >= DATEADD('day', -{days_back}, CURRENT_DATE()) {env_clause}
        ORDER BY summary_date DESC
    """)

    if not quality_daily.empty:
        latest_q = quality_daily.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Flagged requests", f"{latest_q['FLAGGED_REQUEST_PCT']:.1f}%")
        with c2:
            st.metric("Critical", int(latest_q["CRITICAL_COUNT"]))
        with c3:
            st.metric("Warnings", int(latest_q["WARNING_COUNT"]))
        with c4:
            st.metric(
                "7d flagged avg",
                f"{latest_q['ROLLING_7D_FLAGGED_PCT']:.1f}%" if pd.notna(latest_q.get("ROLLING_7D_FLAGGED_PCT")) else "N/A",
            )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Request-level flags (daily)**")
            flag_cols = ["TOOL_LOOPING_COUNT", "EXCESSIVE_STEPS_COUNT",
                         "SLOW_REQUEST_COUNT", "HIGH_TOKEN_BURN_COUNT",
                         "PLANNING_ERROR_COUNT"]
            flag_labels = ["Tool looping", "Excessive steps", "Slow request",
                           "High token burn", "Planning error"]
            qd_sorted = quality_daily.sort_values("SUMMARY_DATE")
            flag_data = pd.melt(
                qd_sorted[["SUMMARY_DATE"] + flag_cols],
                id_vars=["SUMMARY_DATE"],
                var_name="Flag",
                value_name="Count",
            )
            flag_data["Flag"] = flag_data["Flag"].map(dict(zip(flag_cols, flag_labels)))
            chart = alt.Chart(flag_data).mark_bar().encode(
                x=alt.X("SUMMARY_DATE:T", title="Date"),
                y=alt.Y("Count:Q", title="Count"),
                color=alt.Color("Flag:N"),
                tooltip=["SUMMARY_DATE:T", "Flag:N", "Count:Q"],
            )
            st.altair_chart(chart, use_container_width=True)

        with col2:
            st.markdown("**Thread-level flags (daily)**")
            thread_cols = ["SINGLE_TURN_DROPOFF_COUNT", "RAPID_REPHRASING_COUNT",
                           "ABANDONED_COUNT"]
            thread_labels = ["Single-turn drop-off", "Rapid rephrasing", "Abandoned"]
            thread_data = pd.melt(
                qd_sorted[["SUMMARY_DATE"] + thread_cols],
                id_vars=["SUMMARY_DATE"],
                var_name="Flag",
                value_name="Count",
            )
            thread_data["Flag"] = thread_data["Flag"].map(dict(zip(thread_cols, thread_labels)))
            chart = alt.Chart(thread_data).mark_bar().encode(
                x=alt.X("SUMMARY_DATE:T", title="Date"),
                y=alt.Y("Count:Q", title="Count"),
                color=alt.Color("Flag:N"),
                tooltip=["SUMMARY_DATE:T", "Flag:N", "Count:Q"],
            )
            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No interaction quality data available yet.")

    st.subheader("Currently flagged interactions")
    flags = run_query(f"""
        SELECT signal_source, interaction_id, agent_name, user_query,
               event_time, total_duration_ms, total_tokens, steps,
               flags, severity, environment
        FROM RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_FLAGS
        WHERE event_time >= DATEADD('day', -{days_back}, CURRENT_TIMESTAMP()) {env_clause}
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
                 event_time DESC
        LIMIT 100
    """)
    if not flags.empty:
        st.dataframe(flags, hide_index=True)
    else:
        st.success("No flagged interactions in this period.")

with tab_feedback:
    st.header("User feedback trends")

    feedback = run_query(f"""
        SELECT summary_date, environment, agent_or_sv_name,
               total_feedback, positive_count, neutral_count, negative_count,
               avg_rating, negative_pct, rolling_7d_avg_rating,
               rolling_7d_negative_pct
        FROM RETAIL_AI_EVAL.MONITORING.V_FEEDBACK_TREND
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
    st.header("Token usage & costs")

    costs = run_query(f"""
        SELECT metric_date, environment, service_type, agent_or_sv_name,
               total_requests, total_tokens, estimated_cost_usd,
               avg_latency_ms, p95_latency_ms, error_rate_pct,
               rolling_7d_cost_usd, rolling_7d_avg_latency_ms
        FROM RETAIL_AI_EVAL.MONITORING.V_TOKEN_COST_TREND
        WHERE metric_date >= DATEADD('day', -{days_back}, CURRENT_DATE()) {env_clause}
        ORDER BY metric_date DESC
    """)

    if not costs.empty:
        totals = costs.groupby("METRIC_DATE").agg({
            "TOTAL_REQUESTS": "sum",
            "TOTAL_TOKENS": "sum",
            "ESTIMATED_COST_USD": "sum",
        }).reset_index().sort_values("METRIC_DATE")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total cost", f"${costs['ESTIMATED_COST_USD'].sum():,.2f}")
        with c2:
            st.metric("Total tokens", f"{costs['TOTAL_TOKENS'].sum():,.0f}")
        with c3:
            st.metric("Total requests", f"{costs['TOTAL_REQUESTS'].sum():,.0f}")
        with c4:
            st.metric("Avg latency", f"{costs['AVG_LATENCY_MS'].mean():,.0f}ms")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Daily cost by service**")
            chart = alt.Chart(costs.sort_values("METRIC_DATE")).mark_bar().encode(
                x=alt.X("METRIC_DATE:T", title="Date"),
                y=alt.Y("sum(ESTIMATED_COST_USD):Q", title="Cost (USD)"),
                color="SERVICE_TYPE:N",
                tooltip=["METRIC_DATE:T", "SERVICE_TYPE:N", "sum(ESTIMATED_COST_USD):Q"],
            )
            st.altair_chart(chart, use_container_width=True)

        with col2:
            st.markdown("**Daily tokens by service**")
            chart = alt.Chart(costs.sort_values("METRIC_DATE")).mark_area(opacity=0.6).encode(
                x=alt.X("METRIC_DATE:T", title="Date"),
                y=alt.Y("sum(TOTAL_TOKENS):Q", title="Tokens", stack=True),
                color="SERVICE_TYPE:N",
                tooltip=["METRIC_DATE:T", "SERVICE_TYPE:N", "sum(TOTAL_TOKENS):Q"],
            )
            st.altair_chart(chart, use_container_width=True)

        st.markdown("**Latency: avg vs p95**")
        latency_data = costs[["METRIC_DATE", "SERVICE_TYPE", "AVG_LATENCY_MS", "P95_LATENCY_MS"]].copy()
        latency_melt = pd.melt(
            latency_data, id_vars=["METRIC_DATE", "SERVICE_TYPE"],
            var_name="Metric", value_name="Latency (ms)"
        )
        latency_melt["Metric"] = latency_melt["Metric"].map({
            "AVG_LATENCY_MS": "Average", "P95_LATENCY_MS": "P95"
        })
        chart = alt.Chart(latency_melt).mark_line(point=True).encode(
            x=alt.X("METRIC_DATE:T", title="Date"),
            y=alt.Y("Latency (ms):Q"),
            color="SERVICE_TYPE:N",
            strokeDash="Metric:N",
            tooltip=["METRIC_DATE:T", "SERVICE_TYPE:N", "Metric:N", "Latency (ms):Q"],
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No token cost data available yet.")

with tab_alerts:
    st.header("Active alerts")

    active_alerts = run_query(f"""
        SELECT alert_id, alert_type, severity, environment, target_name,
               message, metric_value, threshold_value,
               created_at, hours_since_created
        FROM RETAIL_AI_EVAL.MONITORING.V_ACTIVE_ALERTS
        WHERE 1=1 {env_clause}
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
                 created_at DESC
    """)

    if not active_alerts.empty:
        c1, c2, c3 = st.columns(3)
        crit = len(active_alerts[active_alerts["SEVERITY"] == "CRITICAL"])
        warn = len(active_alerts[active_alerts["SEVERITY"] == "WARNING"])
        with c1:
            st.metric("Critical", crit)
        with c2:
            st.metric("Warning", warn)
        with c3:
            st.metric("Total active", len(active_alerts))

        for _, alert in active_alerts.iterrows():
            severity = alert["SEVERITY"]
            with st.expander(f"{'🔴' if severity == 'CRITICAL' else '🟡'} [{severity}] {alert['ALERT_TYPE']} — {alert['TARGET_NAME']}"):
                st.write(alert["MESSAGE"])
                st.caption(
                    f"Metric: {alert['METRIC_VALUE']} | Threshold: {alert['THRESHOLD_VALUE']} | "
                    f"Created: {alert['CREATED_AT']} ({int(alert['HOURS_SINCE_CREATED'])}h ago)"
                )
    else:
        st.success("No active alerts.")

    st.subheader("Alert history")
    alert_history = run_query(f"""
        SELECT alert_type, severity, environment, target_name,
               message, metric_value, threshold_value,
               acknowledged, created_at
        FROM RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
        WHERE created_at >= DATEADD('day', -{days_back}, CURRENT_TIMESTAMP()) {env_clause}
        ORDER BY created_at DESC
        LIMIT 200
    """)
    if not alert_history.empty:
        st.dataframe(alert_history, hide_index=True)
    else:
        st.caption("No alerts in this period.")

st.caption("Data refreshes every 10 minutes. Powered by RETAIL_AI_EVAL.MONITORING views.")
