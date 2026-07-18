"""Page: Data Quality — table health across bronze/silver/gold layers."""
import streamlit as st
import plotly.express as px

from utils.data_loader import load_data_quality

st.set_page_config(page_title="Data Quality", layout="wide")
st.title("Data Quality Summary")
st.markdown("Health status of all tables across the medallion layers.")

df = load_data_quality()

if df.empty:
    st.info("No quality data available yet. Run the full pipeline first.")
    st.stop()

# Summary metrics
col1, col2, col3 = st.columns(3)
with col1:
    total = len(df)
    st.metric("Total Tables", total)
with col2:
    ok_count = len(df[df["status"] == "ok"]) if "status" in df.columns else 0
    st.metric("Tables OK", ok_count)
with col3:
    missing = len(df[df["status"] != "ok"]) if "status" in df.columns else 0
    st.metric("Tables Missing", missing)

# Detail table
st.subheader("Table Details")
st.dataframe(df, use_container_width=True, hide_index=True)

# Row count chart
if "row_count" in df.columns and "table_name" in df.columns:
    non_empty = df[df["row_count"] > 0].sort_values("row_count", ascending=True)
    if not non_empty.empty:
        fig = px.bar(
            non_empty.tail(30),
            x="row_count",
            y="table_name",
            orientation="h",
            color="layer" if "layer" in df.columns else None,
            title="Row Counts by Table (Top 30)",
            labels={"row_count": "Rows", "table_name": "Table"},
        )
        st.plotly_chart(fig, use_container_width=True)
