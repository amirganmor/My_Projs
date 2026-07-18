"""
NBA Athlete Performance Lakehouse — Streamlit Dashboard
========================================================
Multi-page dashboard showing pipeline results, player rankings,
model metrics, and data quality.
"""
import streamlit as st

st.set_page_config(
    page_title="NBA Athlete Performance Lakehouse",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("NBA Lakehouse")
st.sidebar.markdown("---")
st.sidebar.markdown("""
**Services**
- [Airflow](http://localhost:8080)
- [MinIO](http://localhost:9001)
- [MLflow](http://localhost:5001)
- [Nessie](http://localhost:19120)
""")

st.title("NBA Athlete Performance Lakehouse")
st.markdown("""
### Welcome

This dashboard presents results from a fully local NBA analytics platform that merges
**6 source families** into an Apache Iceberg lakehouse with **bronze / silver / gold**
medallion architecture.

**Analytics Use Cases:**
1. **Underrated Players** — Predicted market value vs actual salary
2. **Improvement Candidates** — Players likely to break out next season
3. **Trade Targets** — Composite-scored trade value rankings

Use the sidebar to navigate between pages.

---

### Architecture Overview

```
6 Source Systems → Airflow DAGs → Bronze (Iceberg) → Silver (Iceberg) → Gold (Iceberg)
                                                                          ↓
                                                              ML Training (MLflow)
                                                                          ↓
                                                              Scored Outputs → Dashboard
```

| Layer | Purpose | Tables |
|-------|---------|--------|
| **Bronze** | Source-shaped raw data | 17 tables |
| **Silver** | Conformed dimensions & facts | 12 tables |
| **Gold** | Analytics marts, features, scores | 12 tables |

### Source Systems

| Source | Type | Description |
|--------|------|-------------|
| NBA API Mock | API (cached JSON) | Official-style player stats, game logs, standings |
| Advanced Metrics | File (CSV) | Efficiency, usage, impact metrics |
| Historical Bulk | File (CSV) | 20-season historical export |
| Shot Charts | File (CSV/JSON) | Zone-level and raw shot data |
| Contracts/Injuries | SQL (PostgreSQL) | Salary, injury, roster records |
| Scouting/Profiles | NoSQL (MongoDB) | Nested scouting reports and player narratives |
""")
