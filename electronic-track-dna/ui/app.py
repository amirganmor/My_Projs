"""Electronic Track DNA Analyzer -- Streamlit UI."""

from __future__ import annotations

import os
import time

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 120.0

st.set_page_config(
    page_title="Track DNA Analyzer",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Track DNA Analyzer")
st.sidebar.markdown("---")
st.sidebar.markdown("""
**Services**
- [Airflow](http://localhost:8080)
- [Qdrant](http://localhost:6333/dashboard)
- [API Docs](http://localhost:8000/docs)
""")


def api_get(path: str, **kwargs):
    try:
        r = httpx.get(f"{API_URL}{path}", timeout=REQUEST_TIMEOUT, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        st.error(f"API error: {e}")
        return None


def api_post(path: str, json_data: dict):
    try:
        r = httpx.post(f"{API_URL}{path}", json=json_data, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        st.error(f"API error: {e}")
        return None


def render_results(data: dict):
    """Render search results as cards."""
    results = data.get("results", [])
    query_desc = data.get("query_description", "")

    if query_desc:
        st.caption(query_desc)

    if not results:
        st.info("No matching tracks found.")
        return

    for i, result in enumerate(results, 1):
        with st.container():
            st.markdown("---")
            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                st.markdown(f"### {i}. {result.get('title', 'Unknown')}")
                artist = result.get("artist") or "Unknown artist"
                st.markdown(f"*{artist}*")

            with col2:
                genres = result.get("genre_tags", [])
                moods = result.get("mood_tags", [])
                if genres:
                    st.markdown(f"**Genre:** {', '.join(genres)}")
                if moods:
                    st.markdown(f"**Mood:** {', '.join(moods)}")

            with col3:
                score = result.get("score", 0)
                st.metric("Score", f"{score:.3f}")

            summary = result.get("summary", "")
            if summary:
                st.markdown(f"> {summary[:300]}")

            explanation = result.get("explanation", "")
            if explanation:
                with st.expander("Why this matches"):
                    st.markdown(explanation)


# ── Tabs ─────────────────────────────────────────────────────
tab_ingest, tab_search, tab_library = st.tabs(["Ingest", "Search", "Library"])

# ── Ingest Tab ───────────────────────────────────────────────
with tab_ingest:
    st.header("Ingest YouTube Tracks")
    st.markdown("Paste YouTube URLs (one per line) to analyze and index.")

    urls_input = st.text_area(
        "YouTube URLs",
        height=150,
        placeholder="https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...",
    )

    if st.button("Analyze Tracks", type="primary"):
        urls = [u.strip() for u in urls_input.strip().split("\n") if u.strip()]
        if not urls:
            st.warning("Please enter at least one URL.")
        else:
            with st.spinner(f"Submitting {len(urls)} URL(s) to pipeline..."):
                result = api_post("/ingest", {"urls": urls})

            if result:
                st.success(
                    f"Pipeline triggered. DAG run: `{result.get('dag_run_id', 'N/A')}`"
                )
                dag_run_id = result.get("dag_run_id")
                if dag_run_id:
                    st.markdown("### Pipeline Status")
                    status_placeholder = st.empty()
                    for _ in range(60):
                        status = api_get(f"/ingest/{dag_run_id}/status")
                        if status:
                            state = status.get("state", "unknown")
                            status_placeholder.info(f"State: **{state}**")
                            if state in ("success", "failed"):
                                if state == "success":
                                    st.success("Pipeline completed successfully!")
                                else:
                                    st.error("Pipeline failed. Check Airflow logs.")
                                break
                        time.sleep(5)

# ── Search Tab ───────────────────────────────────────────────
with tab_search:
    st.header("Search Indexed Tracks")

    search_mode = st.radio(
        "Search Mode",
        ["Free-text", "Similar to YouTube URL", "Similar + Refinement"],
        horizontal=True,
    )

    if search_mode == "Free-text":
        query = st.text_input(
            "Describe the sound you're looking for",
            placeholder="dark melodic techno with long intro and strong bass",
        )
        limit = st.slider("Max results", 1, 20, 5)

        if st.button("Search", type="primary"):
            if not query:
                st.warning("Enter a search query.")
            else:
                with st.spinner("Searching..."):
                    data = api_post("/search/text", {"query": query, "limit": limit})
                if data:
                    render_results(data)

    elif search_mode == "Similar to YouTube URL":
        url = st.text_input(
            "YouTube URL",
            placeholder="https://youtube.com/watch?v=...",
        )
        limit = st.slider("Max results", 1, 20, 5, key="sim_limit")

        if st.button("Find Similar", type="primary"):
            if not url:
                st.warning("Enter a YouTube URL.")
            else:
                with st.spinner("Analyzing track and searching..."):
                    data = api_post("/search/similar", {
                        "youtube_url": url, "limit": limit,
                    })
                if data:
                    render_results(data)

    else:
        url = st.text_input(
            "YouTube URL",
            placeholder="https://youtube.com/watch?v=...",
            key="ref_url",
        )
        refinement = st.text_input(
            "Refinement",
            placeholder="darker and less vocal",
        )
        limit = st.slider("Max results", 1, 20, 5, key="ref_limit")

        if st.button("Search Refined", type="primary"):
            if not url or not refinement:
                st.warning("Enter both a URL and refinement text.")
            else:
                with st.spinner("Analyzing, refining, and searching..."):
                    data = api_post("/search/similar-refined", {
                        "youtube_url": url,
                        "refinement": refinement,
                        "limit": limit,
                    })
                if data:
                    render_results(data)

# ── Library Tab ──────────────────────────────────────────────
with tab_library:
    st.header("Track Library")

    if st.button("Refresh Library"):
        st.rerun()

    tracks_data = api_get("/tracks")
    if tracks_data and tracks_data.get("tracks"):
        st.markdown(f"**{tracks_data['count']}** tracks indexed")

        for track in tracks_data["tracks"]:
            with st.expander(
                f"🎵 {track['title']} — {track.get('artist') or 'Unknown'}",
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**YouTube ID:** `{track['youtube_id']}`")
                    st.markdown(
                        f"**Genre:** {', '.join(track.get('genre_tags', [])) or 'N/A'}"
                    )
                with col2:
                    st.markdown(
                        f"**Mood:** {', '.join(track.get('mood_tags', [])) or 'N/A'}"
                    )

                if st.button(
                    "View Full DNA",
                    key=f"dna_{track['youtube_id']}",
                ):
                    detail = api_get(f"/tracks/{track['youtube_id']}")
                    if detail:
                        st.json(detail)
    else:
        st.info("No tracks indexed yet. Use the Ingest tab to add some!")
