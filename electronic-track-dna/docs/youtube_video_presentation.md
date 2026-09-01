# YouTube Video Presentation Plan — Electronic Track DNA Analyzer

## Recommended Format

**Target length:** 25–32 minutes (architecture + live ingest + three search modes + extended “next level” vision).

**Style:** Screen recording with voiceover. Clear YouTube chapters via timestamps. Face cam optional.

**Demo prep:** Pre-index **~10–16** electronic tracks so search is interesting. Have 1–2 *new* URLs ready for live ingest / similar-to-YouTube. Prefer clean `https://www.youtube.com/watch?v=ID` links (no playlist `&list=`).

**Current system posture (film this):** After ingest, **raw audio and WAVs are deleted**. What remains is Qdrant vectors + DNA reports. Search does not need library audio on disk.

---

## Video Structure (9 Chapters)

---

### Chapter 1 — Hook + What This Project Does (1–2 min)

Open with the **end result first** — Streamlit Search tab (`http://localhost:8501`):

- Free-text: `"driving trance peak-time"` (or `"dark melodic techno with long intro"`)
- Result cards with score, genre/mood tags, structured “why this matches”
- Briefly flip to Library with indexed tracks
- Optional one-liner: Library holds **vectors + reports**, not a music archive

Then flash the architecture one-liner from the README.

**SPEECH:**

> What you're looking at is a local AI that *listens* to electronic music — and then helps you find the next track by how it *sounds*, not by how someone titled the YouTube video.
>
> Here's the move. You paste links. The system analyzes the waveform — tempo, energy, structure — builds a Track DNA profile, and stores two kinds of fingerprints so you can search like a DJ who actually heard the set, not like a keyword bot.
>
> Watch this. I type: “driving trance peak-time.” Boom — ranked results. These aren't title matches. The pipeline measured the audio, wrote a searchable description from those measurements, and found neighbors in meaning-space. Separately, I can paste another YouTube URL and ask: “what in my library sounds like *this*?” That uses CLAP — an audio model that actually listened.
>
> And the design twist that matters: after analysis, we **delete the audio**. What stays is DNA text, reports, and vectors — not a pile of ripped files. Analysis in. Fingerprint out. File gone.
>
> All of this runs on my laptop with Docker Compose: Airflow, Qdrant, FastAPI, Streamlit. No cloud LLM bill. No Spotify API. URL in — Track DNA and searchable vectors out.
>
> In this video: architecture, the full data flow, the code, a live ingest, all three search modes, and how I'd take this from laptop demo to “go big.” Let's go.

---

### Chapter 2 — Architecture Overview (2–3 min)

Walk the stack:

| Layer | Tech | Role |
|-------|------|------|
| Orchestration | Airflow | Ingest DAG for one or many URLs (mapped tasks) |
| API / UI | FastAPI + Streamlit | Trigger + search + library |
| Vector DB | Qdrant | Named vectors: `audio` (512) + `text` (384) |
| Audio ML | CLAP | Similar-to-YouTube / audio similarity |
| Text ML | MiniLM | Free-text over template `search_text` |
| Features | yt-dlp, ffmpeg, librosa | **Ephemeral** stream → analyze (BPM, sections, CLAP) → **discard audio** |

**Key design point:** We deliberately **removed Ollama**. Chat LLMs for “describe this spectrogram” are slow, heavy, and weakly grounded. Audio-first: CLAP on the waveform; templates for DNA text; MiniLM for text queries.

**Copyright framing (say this in Chapter 2):** Personal portfolio demo only. yt-dlp is an open-source extractor ([yt-dlp on GitHub](https://github.com/yt-dlp/yt-dlp)) — a tool, not a product goal. Audio exists only in memory/disk long enough to compute features and embeddings, then is deleted. You keep **analysis artifacts** (Track DNA, vectors), not a music library.

Show `docker compose ps` — postgres, qdrant, airflow, api, ui (no ollama).

**SPEECH:**

> **[SCREEN: Architecture diagram from docs/design.md or README]**
>
> Here's the stack. User hits Streamlit or the FastAPI docs. Ingest doesn't run heavy analysis inside the web request — it triggers an Airflow DAG with a list of YouTube URLs. That matters: waveform analysis and CLAP embedding can take minutes per track. Airflow owns the batch pipeline; FastAPI owns interactive search.
>
> **CLAP** — Contrastive Language-Audio Pretraining — is a neural model trained to map audio and text into the same embedding space. Here we only use the audio side: it listens to a short slice of the waveform and outputs a fixed-size vector (512 numbers) that captures timbre, rhythm, and energy — so “sounds like this track” becomes a nearest-neighbor search in Qdrant, not a title keyword match.
>
> For the **input side**, I use **yt-dlp** — the open-source project on GitHub, maintained by the community. It's a URL resolver and media extractor: given a YouTube link, it gives the pipeline a byte stream we can analyze. I'm not building a ripper or a music archive. The point is **Track DNA** — tempo, energy, structure, embeddings — not keeping MP3s.
>
> **Copyright and how I avoid crossing the line in this demo:** This is a personal, local portfolio project — not a public download service. I only process URLs I paste for analysis. Audio is **ephemeral**: analyze, embed, write the DNA report, then delete the file. What persists is vectors in Qdrant and JSON/Markdown reports — measurable metadata, not redistributable audio. I don't ship tracks, don't host a library of files, and I'm not affiliated with YouTube. In a real product you'd use licensed catalogs or user-owned uploads; YouTube here is just a convenient demo input.
>
> Storage is Qdrant with **two named vectors per track**. The `audio` vector is CLAP — about 512 dimensions — used when you say “find tracks that sound like this YouTube link.” The `text` vector is MiniLM — 384 dimensions — used when you type natural language. Same Track DNA payload on both: tempo, sections, tags, summary.
>
> **[SCREEN: docker compose ps]**
>
> One compose file. Postgres for Airflow metadata, Qdrant for vectors, Airflow webserver and scheduler, API, Streamlit. HuggingFace model weights cache in a shared volume — that's model binaries, not your music.
>
> Why not just embed video titles with an LLM? Because titles lie — “Best Techno Mix 2024” tells you nothing about intro length or bass. We **analyze the waveform**, derive features, then search on those measurements.

---

### Chapter 3 — Data Flow Deep Dive: URL → Track DNA → Qdrant (6–7 min)

This is the core engineering chapter — keep energy high. Follow `docs/design.md` and Airflow graph. Spend extra time on **CLAP** and **Qdrant** (the “wow” of the pipeline).

1. Validate URL / YouTube ID; skip if already in Qdrant  
2. yt-dlp → ephemeral audio (`noplaylist`; alternate player clients on HTTP 403)  
3. ffmpeg → mono WAV @ 22.05 kHz (features) / CLAP uses 48 kHz load  
4. librosa → AudioFeatures  
5. Section detector → intro / buildup / drop / breakdown / outro  
6. Templates → genre/mood tags, `search_text`, `summary`  
7. CLAP embed + MiniLM embed → upsert Qdrant  
8. JSON/Markdown reports under `data/reports/`  
9. **Cleanup** → delete `data/raw_audio/{id}.*` and `data/wav/{id}.wav`

**Resilience (mention briefly):** Per-URL failures raise `AirflowSkipException` so one bad YouTube 403 does not fail the whole batch. Downloads are capped at **3 concurrent** mapped tasks to reduce rate-limits when pasting ~20 URLs.

**SPEECH:**

> **[SCREEN: Mermaid / design diagram — full pipeline]**
>
> Okay — this is the fun part. One YouTube link walks in. A searchable Track DNA walks out. Let's follow that journey like a relay race — every task hands the baton to the next.
>
> **[SCREEN: Airflow DAG graph for `track_dna_dag`]**
>
> **Task one — validate.** We pull the eleven-character YouTube ID — that tiny string is our primary key. Already in Qdrant? Skip. No drama, no double work. Idempotent ingest is boring… and that's a compliment.
>
> **Task two — ephemeral fetch.** yt-dlp resolves *one* video — `noplaylist` so a shared playlist link doesn't summon fifty surprise tracks. YouTube throws a 403? We shrug and retry with alternate player clients. ffmpeg turns the stream into a clean mono WAV. Think of that WAV as a **lab sample**: needed for the experiment, not for the museum.
>
> **Task three — features.** librosa is our microscope. Tempo BPM, RMS energy mean and std, spectral centroid, bandwidth, rolloff, thirteen MFCCs, chroma, zero-crossing rate, onset rate, duration, approximate loudness. Suddenly the track stops being “a vibe” and becomes a spreadsheet of physics. *That* spreadsheet is the quantitative DNA.
>
> **Task four — sections.** No mysterious black-box structure model. We slide energy across roughly four-second frames, catch the jumps, and stamp labels: intro, buildup, drop, breakdown, outro. Electronic music *lives* on energy curves — so a heuristic that reads the curve is both honest and explainable. When someone asks “why long intro?” you can point at the section table, not vibes.
>
> **Task five — Track DNA assembly.** Heuristics slap on genre tags from BPM and spectral shape — techno, dark, hypnotic, the usual suspects. Mood tags, a keyword-rich `search_text`, and a short summary come from **templates**, not a chatty LLM. Fast, deterministic, repeatable. Same track in → same DNA out. Boring again — in the best way.
>
> **Task six — dual embed… and here's where CLAP steals the show.**
>
> **[SCREEN: `src/embeddings.py` — CLAP load + `embed_audio`; optional: tiny diagram "waveform → 512-d vector"]**
>
> CLAP stands for **Contrastive Language-Audio Pretraining**.
>
> The core idea is simple. CLAP was trained on millions of pairs like: *(this audio clip)* + *(a short text description of that clip)*. During training it learns two encoders — one for audio, one for text — that both output vectors in the **same shared space**.
>
> For a **matching** pair (the caption really describes the sound), the two vectors are pulled **closer**. For a **mismatched** pair (random caption + unrelated sound), they are pushed **farther apart**. After enough of that, vectors for similar sounds — and for language that describes those sounds — end up in the same neighborhood.
>
> Concrete example: the phrase `"dark driving techno"` and a clip that actually *is* dark driving techno get similar vectors. A soft ambient pad gets a very different vector. The model does **not** need to have heard that exact track before — it generalizes from patterns in the training data.
>
> One-line summary of contrastive learning: **related → close in space; unrelated → far apart.**
>
> In *this* project we mostly use the **audio encoder** (sometimes called the audio tower). We are not asking CLAP to generate text. We ask it to **listen** and emit a fingerprint.
>
> What the pipeline does: load the WAV, resample to **48 kHz**, take up to a centered **~30-second window**, run that window through CLAP's audio encoder, and get back one **512-dimensional vector** — 512 numbers that encode timbre, rhythm feel, density, brightness, how hard the track hits. That vector is the track's *sonic fingerprint* for similarity search.
>
> Why only ~30 seconds, not the full seven-minute track? Electronic tracks change a lot over time — long intros, late drops, long outros. A centered window is a practical tradeoff: capture the main body without huge memory and latency cost. Honest limit: an hour-long mix still becomes a snapshot of the middle. Chapter 8's upgrade path is multi-segment embeddings (separate vectors for intro vs drop).
>
> Separately, MiniLM embeds our template `search_text` into a **384-dimensional** vector. Same track, two fingerprints: CLAP for **"sounds like this"**, MiniLM for **"reads like this"**. Both attach to the same Track DNA payload in Qdrant.
>
> At search time we use **cosine similarity**: how aligned are two vectors? High score → related. Low score → not related. That is content-based search — no genre taxonomy required at query time.
>
> **Task seven — Qdrant: the club where vectors hang out.**
>
> **[SCREEN: Qdrant dashboard / `src/qdrant_store.py` — named vectors `audio` + `text`; show one point with payload]**
>
> Qdrant is our vector database — think of it as a **nightclub with two dance floors under one roof**. Floor one is named `audio` (512-d Cosine). Floor two is named `text` (384-d Cosine). Every track is one **point**: one ID, one **payload** (the full Track DNA JSON — title, BPM, sections, tags, summary, search text), and **two vectors** stapled to that same point.
>
> Why named vectors instead of two collections? Because the payload stays unified. Search can say `using="audio"` or `using="text"` without juggling duplicate metadata. Upsert is atomic-ish from the app's view: write both embeddings + payload together. Point ID is a stable hash of the YouTube ID — same video always lands on the same seat. Re-ingest? Overwrite, don't clone.
>
> What happens at search time? You hand Qdrant a query vector and ask for the top-k nearest neighbors on one floor. Under the hood it uses **approximate nearest neighbor (ANN)** indexes — HNSW-style graph search — so "find the five closest fingerprints" stays fast even when the library grows past a laptop demo. For this portfolio scale it's instant; the design already thinks past sixteen tracks.
>
> The payload is not decoration. Result cards, tags, BPM, "why this matched" — all come from that JSON sitting next to the vectors. Vectors find the neighbors; DNA explains them.
>
> Side by side we also write `data/reports/{id}.json` and `.md` — the human-readable twin of the payload. Engineers get vectors; humans get a markdown autopsy of what the machine heard. Perfect for the video — open the report, show the evidence.
>
> **Task eight — cleanup: the responsible encore.**
>
> Once the vectors and reports exist, the WAV has finished its shift. We delete the ephemeral audio. Free-text search never needed the file again — it only needs the MiniLM vector and the DNA text. Similar-to-URL? Fresh query analysis on demand, then that temporary audio gets deleted too.
>
> So the lasting artifacts are: **Qdrant points + reports**. Not a music dump. Analysis in, fingerprint out, audio gone. That's the product ethic of this demo — and it's what lets you talk about copyright calmly: we kept the *analysis*, not the soundtrack.
>
> **[SCREEN: Open a sample report markdown; empty `data/wav` is fine]**
>
> Look at that report — title, BPM, section table, tags, search text. Free-text search is really matching against *this* grounded story. Audio search is matching against CLAP's 512-d fingerprint on Qdrant's `audio` floor. Two doors into the same nightclub. That's the pipeline. Let's open those doors in search.


---

### Chapter 4 — Three Search Modes (4–5 min)

Live demos in Streamlit + optional curl / Swagger. This is the payoff — show all three doors into the same Qdrant nightclub.

1. **Free-text** → MiniLM → `text` vector → template explanation  
2. **Similar-to-YouTube** → analyze URL → CLAP → `audio` vector (query audio deleted afterward)  
3. **Similar + refinement** → audio candidate pool → re-rank with MiniLM vs refinement (≈0.7 audio / 0.3 text)

**Swagger mapping (if you show `/docs`):**

| Mode | Endpoint | Body |
|------|----------|------|
| Free-text | `POST /search/text` | `{"query": "...", "limit": 5}` |
| Similar | `POST /search/similar` | `{"youtube_url": "https://...", "limit": 5}` |
| Refined | `POST /search/similar-refined` | `{"youtube_url": "...", "refinement": "...", "limit": 5}` |

Note: `/search/text` is **words only** — a YouTube URL belongs on `/search/similar`.

**SPEECH:**

> **[SCREEN: Streamlit Search — Free-text]**
>
> Mode one — free text. I type: “driving trance peak-time.” MiniLM embeds that sentence into the **text** floor. Qdrant finds the nearest Track DNA paragraphs — not video titles. The explanation isn't ChatGPT inventing a story — it's structured: overlapping tags, BPM cues, intro length. You can trust it because it cites features we measured.
>
> **[SCREEN: Similar to YouTube URL]**
>
> Mode two — similar-to-YouTube. I paste a URL that may not even be in the library. The API analyzes it on the fly — ephemeral fetch, features, CLAP audio vector — then asks Qdrant on the **audio** floor: which indexed tracks are nearest in sonic space? Then it deletes that temporary audio. That's content-based retrieval, not metadata matching — and still no lasting music archive.
>
> First call can take a minute while models warm and the query track is analyzed. After that it feels snappy. Watch the ranked list — scores, tags, summaries. Same DNA payload, different door.
>
> **[SCREEN: Similar + Refinement]**
>
> Mode three — similar + refinement. Same YouTube URL, plus a natural-language tweak: “like this, but darker and less vocal” or “harder drop.” Under the hood we pull a **wider** audio neighbor pool from CLAP — say fifteen candidates — then re-rank with MiniLM against the refinement phrase. Rough blend: about **0.7 audio / 0.3 text**. Sound similarity first, language steering second. That's hybrid search without a heavy reranker LLM.
>
> Watch how the ranking shifts versus plain similar. Same query track, different top hits — that's the product magic.
>
> **[SCREEN: FastAPI /docs briefly]**
>
> Same three endpoints under `/search/text`, `/search/similar`, `/search/similar-refined`. Streamlit is a thin client over FastAPI. If you're demoing for engineers, hit Try it out in Swagger and show the JSON — scores, genre_tags, mood_tags, explanation. UI for storytelling; API for proof.

---

### Chapter 5 — Code Walkthrough (3–4 min)

Project tree; thin DAG; fat `src/`.

**SPEECH:**

> **[SCREEN: Project tree]**
>
> `dags/` — one TaskFlow DAG, mapped over URLs. `src/` — downloader, audio_features, section_detector, text_generator, embeddings, qdrant_store, search, explain. `api/` and `ui/` — FastAPI and Streamlit. `infra/` — Dockerfiles. `data/` — features + reports (raw/wav are ephemeral).
>
> **[SCREEN: `dags/track_dna_dag.py`]**
>
> Thin orchestration. Validate expands into download → features → sections → build DNA → embed_and_store → save reports → **cleanup_audio**. Per-stage errors on one URL become **skips**, not hard fails, so a batch of twenty links can partially succeed. Download concurrency is capped at three.
>
> **[SCREEN: `src/downloader.py` — cleanup + yt-dlp options]**
>
> `noplaylist`, player-client fallbacks for 403s, and `cleanup_audio_files` that removes raw + WAV by YouTube ID.
>
> **[SCREEN: `src/embeddings.py`]**
>
> Lazy-loaded models. First call downloads CLAP and MiniLM into `/hf-cache`. Embeddings L2-normalized for cosine in Qdrant.
>
> **[SCREEN: `src/qdrant_store.py`]**
>
> Collection created with named vectors `audio` and `text`. Upsert writes both. Search takes `using="audio"` or `using="text"`.
>
> **[SCREEN: `src/search.py` — refined search + finally cleanup]**
>
> Hybrid retrieval without a reranker LLM — and query audio cleaned in a `finally` block.
>
> Takeaway: Airflow for batch, FastAPI for sync search, dual vectors for two query types, templates instead of LLM prose, vectors retained — audio discarded.

---

### Chapter 6 — Live Ingest Demo (4–5 min)

Start from a cold(ish) stack so viewers see the full “bring it up → paste URLs → green tasks → library grows” loop.

1. Terminal: `docker compose up -d` (or `ps` if already running)  
2. Unpause `track_dna_dag` if needed  
3. Streamlit Ingest — paste **several** URLs (demo: 3–5 live; system supports ~20 with skips)  
4. Watch Airflow graph: successes green, blocked videos **skipped**  
5. Library refresh + open report  
6. Optional: empty `data/wav` + Qdrant point count up  

**SPEECH:**

> **[SCREEN: Terminal — project folder]**
>
> Demo time. No slides — we boot the machine.
>
> **[SCREEN: `docker compose up -d` / `docker compose ps`]**
>
> One command. Docker Compose lights up the whole band: Postgres, Qdrant, Airflow webserver and scheduler, the API, Streamlit. If it's already warm, `docker compose ps` — green checks, we're live. First-ever boot can take a minute while images settle; after that it's coffee-break fast.
>
> **[SCREEN: Airflow UI — unpause `track_dna_dag` if paused]**
>
> Airflow is the stage manager. Open http://localhost:8080 — login is **admin** / **admin**. Unpause the DAG so ingest can actually run. Then we're ready to feed it tracks.
>
> **[SCREEN: Streamlit http://localhost:8501 — Ingest tab]**
>
> Open the UI. Ingest tab. Paste a handful of clean YouTube links — three to five is perfect on camera. Hit Analyze. Behind the curtain that fires `POST /ingest`, which creates an Airflow DAG run with those URLs in the config. You didn't just click a button — you kicked a real batch pipeline.
>
> **[SCREEN: Airflow — running DAG / mapped tasks]**
>
> Flip to Airflow. Watch the mapped tasks light up. Downloads run a few at a time so YouTube doesn't rage-quit with 403s. One video blocked? That map index **skips** — the rest keep cooking. Partial success is a feature, not a bug. When reports finish, cleanup deletes the ephemeral audio. Vectors stay. Files don't.
>
> **[SCREEN: Streamlit Library + open a report; optional empty `data/wav`, Qdrant dashboard]**
>
> Back to Library — refresh. New tracks appear, pulled from Qdrant. Open a markdown report: BPM, sections, tags, search text. That's the evidence. Optional flex: show `data/wav` empty, point count up in Qdrant. Analysis in. Fingerprint out. Audio gone.
>
> Closed loop, live on camera: **compose up → paste URLs → green tasks → DNA in the library → ready to search.** That's the product. Next we talk about *why* we built it this way.

---

### Chapter 7 — Design Decisions & Tradeoffs (2–3 min)

Talking over diagram / short bullet slide.

**SPEECH:**

> A few decisions worth defending in an interview.
>
> **Why dual vectors?** Text queries and audio queries live in different spaces. Forcing one embedding type loses one of the two products. MiniLM answers “driving trance”; CLAP answers “sounds like this URL” — same payload, two doors.
>
> **Why templates not LLMs?** For Track DNA prose we need consistency and speed. Features already encode the truth; templates verbalize them. Explanations cite BPM and spectral deltas — auditable. Same track twice → same DNA text; no hallucinated genres from a chat model.
>
> **Why Airflow for ingest but not for search?** Ingest is long-running and retryable. Search must feel interactive. Similar-to-URL analysis runs in the API process on demand. Batch gets retries and mapped skips; search gets milliseconds, not DAG-run latency.
>
> **Why heuristic sections?** Electronic music is energy-driven. Full MIR structure models are heavier; heuristics are good enough for “long intro” style queries. You can point at the energy curve and defend the label — great for demos and interviews.
>
> **Why skip instead of fail on one bad URL?** Batch UX. Pasting twenty links shouldn't die because YouTube blocked one file. Partial success still grows the library; red-fail-the-world would kill the demo.
>
> **Why delete audio after ingest?** Search only needs vectors and DNA text. Keeping WAVs would make this look like a download archive. For a personal portfolio demo, ephemeral audio is the cleaner design. Copyright story stays simple: analysis in, fingerprint out, file gone.
>
> **Limits today — and why that's exciting:** YouTube availability, a CLAP window instead of a full hour mix, heuristic tags, no accounts or playlists yet. That's not a failure mode — that's the scope of a **laptop-powered portfolio system** pushed as far as local Docker, local models, and local Qdrant can honestly go. Next: if we took the same architecture and removed the laptop ceiling — what would “go big” look like?

---

### Chapter 8 — Taking It to the Next Level (6–7 min)

**Purpose:** Show you can think beyond the laptop demo — product vision, ML upgrades, platform scale, and how you’d *measure* success. This is the “senior engineer / PM brain” chapter.

**On-screen:** Simple roadmap slide or whiteboard with four lanes: **Models → Product → Platform → Evaluation**. Optionally flash `docs/design.md` architecture once and say “same boxes, bigger boxes.”

---

#### 8.1 — Anchor: what stays the same (≈45 sec)

**SPEECH:**

> Before the wish list — what I would **not** throw away.
>
> The product idea is simple and it stays: take a track, measure what it sounds like, store that as searchable fingerprints, and let people find music by text or by similarity. The three search modes stay. The idea that we keep analysis results — not a pile of audio files — stays.
>
> How the boxes are wired also stays: a batch pipeline for ingest, a fast API for search, a vector database for fingerprints. Tomorrow we might swap the audio model, add better section detection, or run on Kubernetes — but we shouldn't need a rewrite from scratch.
>
> In other words: keep the design, upgrade the parts. That's how you grow a real system.

---

#### 8.2 — Richer audio intelligence (≈1.5 min)

**On-screen:** Diagram: one track → multiple segment vectors (intro / drop / breakdown). Optional: CLAP vs MusicFM / OpenL3 comparison table.

| Today | Next level |
|-------|------------|
| Single CLAP vector from ≤30 s centered window | Multi-segment embeddings per section |
| General music+speech CLAP | Fine-tuned or music-native encoders |
| Heuristic genre/mood tags | Learned tags + calibrated confidence |

**SPEECH:**

> **Problem today:** CLAP hears a thirty-second window from the middle of the track. For a seven-minute progressive trance journey, that’s a snapshot — great for “roughly sounds like this,” weak for “long intro” or “drop at 4:30.”
>
> **Multi-segment vectors.** Run the section detector — or a better boundary model — and embed *each* section separately. Store named vectors like `intro`, `drop`, `breakdown` in Qdrant, or store a small set of segment points linked by `youtube_id`. Search becomes: “find tracks whose *intro* matches this reference intro” — that’s a DJ-native query.
>
> **Better encoders.** Fine-tune CLAP on a techno/house corpus so embeddings aren’t generic. Or evaluate MusicFM, OpenL3, or newer music transformers. You’d A/B them on a labeled similarity set — same architecture, different `embed_audio()` implementation.
>
> **Richer DNA, not LLM fluff.** Add key detection, vocal presence score, stereo width, sub-bass energy band. Feed those into templates *or* a small classifier head trained on labeled subgenres. The point is measurable fields that refinements can actually filter on — “less vocal” should mean `vocal_activity < 0.2`, not hope the text embedding guesses.

---

#### 8.3 — Better structure & MIR (≈1 min)

**On-screen:** Side-by-side: current energy-heuristic sections vs learned boundary timeline.

**SPEECH:**

> **Sections today** are explainable but crude — RMS frames and thresholds. Good for electronic music demos; not festival-grade structure analysis.
>
> **Upgrade path:** madmom beat/downbeat tracking, all-in-one structure models, or a lightweight CNN trained on EDM segment labels. Output the same `Section` schema so downstream DNA and search don’t break — classic strangler pattern.
>
> **Vocal activity detection** unlocks refinement queries that actually work: “like this but instrumental,” “more vocal hook.” Today we re-rank on text; tomorrow we filter on a numeric vocal score before vector search.
>
> **Tempo stability & energy curve** as first-class features — not just mean BPM but “does the energy ramp for two minutes then slam?” That’s playlist logic, not just similarity.

---

#### 8.4 — Product: hybrid search & DJ workflows (≈1.5 min)

**On-screen:** Mock UI: BPM slider + key filter + text box + “build set” button. Flow: hard filters → vector search → rerank → playlist export.

**SPEECH:**

> **Hybrid retrieval** is where this becomes a product, not a science project.
>
> Step one — **hard filters:** BPM range, duration, “has long intro,” vocal score, maybe camelot key compatibility. Cheap SQL or Qdrant payload filters *before* ANN search. DJs don’t want “similar at 128 BPM” when they’re mixing at 138.
>
> Step two — **vector search** on the filtered subset — audio or text space, same as now.
>
> Step three — **smarter ranking.** Today our “refined” search is a fixed mix: about 70% audio similarity, 30% text. In production, a small model would learn those weights from real choices — like “a DJ played track A, then picked track B next.” It looks at how close the sound is, how well the text matches, BPM difference, musical key, and whether the energy rises smoothly — then ranks what actually works in a set.
>
> **Building a set, not just a list.** Right now we return “tracks like this one.” Next step: suggest the *next* track in a mix. “I just played A — what should come after, with a bit more energy, without a harsh key jump?” Same fingerprints underneath; we just score a *path* of tracks, not one track alone.
>
> **Where the music comes from.** YouTube was only a convenient demo input. A real product would use files the user uploads (music they own) or a licensed catalog API. The rest of the pipeline stays the same — only the “get the audio” step changes.
>
> **Keep the ‘why’ visible.** Results still show BPM, sections, and tags. The smarter ranker just adds plain-language reasons like “compatible key” or “energy steps up” — so the DJ trusts the suggestion, not a black box.

---

#### 8.5 — Platform & scale (≈1 min)

**On-screen:** K8s diagram: ingest workers, GPU embedding pool, Qdrant cluster, API gateway. Mention Kafka arrow from “new release event” to Airflow/K8s job.

**SPEECH:**

> **Ingest at scale.** Today one laptop worker does the heavy lifting. Next level: many workers in Kubernetes. When the queue of new tracks grows, the cluster spins up more machines. Split the work: normal CPUs for ffmpeg and librosa, GPUs for CLAP embedding. Same pipeline steps — just more hands doing them in parallel.
>
> **Storage.** If you have the rights, keep audio only briefly in cloud storage while you analyze it — then delete it, same as now. Keep reports and features in a data warehouse if you want charts across the whole catalog: average BPM by label, how many long intros, and so on.
>
> **Qdrant grows with you.** One node on a laptop is fine for a demo. For a big catalog: a cluster with copies for safety, maybe split collections by genre or label, and separate collections if you store intro/drop segments as their own vectors.
>
> **A tougher API.** Add login, rate limits, and background jobs for “analyze this YouTube URL.” Instead of the browser waiting three minutes, the API says “we’re on it” and notifies you when the result is ready.
>
> **Always-on ingest.** A stream of “new release” events — from Beatport, Bandcamp, or your own catalog — triggers analysis automatically. Fresh tracks get fingerprints within minutes. That’s a living “new underground” feed you can search by sound, not just by release date.

---

#### 8.6 — Evaluation & iteration (≈1 min)

**On-screen:** Simple metrics slide: Recall@5, MRR, DJ agreement %. A/B table for refinement weights.

**SPEECH:**

> **You can’t improve what you don’t measure.**
>
> Start with a **test set of truth:** a few hundred labeled examples. “This query should return that track.” “This URL should be close to Y, not Z.” You and a friend who DJs can label them. Then measure: how often is the right track in the top 5? Do that separately for text search and audio search — they fail in different ways.
>
> **Offline loop.** Try a new audio model or better section detector → re-embed the library overnight → run the test set → keep the change only if the scores go up. Same idea as recommender systems: change → measure → promote or reject.
>
> **Online A/B.** Show half the users today’s fixed 70/30 blend, half the learned ranker. Log what they click and what they add to a crate. Real behavior beats gut feel.
>
> **When results are wrong, sort the failures.** Was the BPM filter too strict? Did CLAP only hear the middle of the track? Bad genre tag? Bad YouTube upload quality? Each bucket points to a clear fix — better features, better filters, or better training data.
>
> That’s how the laptop demo earns trust in an interview: you’re not stacking buzzwords — you have a closed loop: ship → measure → improve.

---

#### 8.7 — Close the vision (≈30 sec)

**SPEECH:**

> So — unlimited budget, same architecture.
>
> Smarter ears: multi-segment and fine-tuned embeddings.
> Smarter structure: real MIR boundaries and vocal scores.
> Smarter product: filters, rerankers, playlist logic.
> Smarter platform: K8s, Kafka, Qdrant cluster, licensed inputs.
> Smarter process: golden sets and recall@k.
>
> The demo on my laptop proves the loop works. The next level proves you know how to **operate** it. Let’s wrap with how you run the demo yourself.

**Optional B-roll:** Quick montage — Streamlit search → Airflow graph → Qdrant dashboard → empty `data/wav` folder — while saying “vectors, not MP3s.”

---

### Chapter 9 — How to Run It + Closing (1–2 min)

**SPEECH:**

> **[SCREEN: README]**
>

> Clone the repo, copy `.env`, `docker compose up -d --build`, unpause `track_dna_dag`, open localhost:8501. First ingest pulls HuggingFace models into the cache volume. If you upgrade from the old Ollama version, wipe the Qdrant volume so named vectors recreate cleanly.
>
> **[SCREEN: Search results one last time]**
>
> Full code on GitHub — link in the description. If you're building a portfolio: this shows Docker Compose platforms, Airflow TaskFlow, audio ML, vector search, resilient mapped batches, and a real product UX — without pretending a chat LLM is doing the listening, and without keeping a music dump on disk.
>
> See you in the next one.

---

## Production Tips

- **Screen recording:** OBS or QuickTime, 1080p+.
- **Pre-open tabs:** Streamlit, Airflow, FastAPI `/docs`, Qdrant dashboard, VS Code, terminal.
- **Pre-index tracks:** Don't make the whole video wait on first CLAP download — do one warm ingest before recording (~10–16 tracks is a good demo library).
- **Demo URLs:** Prefer official audio / label channels that stay available; have backups. Use clean `watch?v=` URLs.
- **Batch demo:** You *can* paste many URLs; expect some **skipped** map indices on YouTube 403s — call that out as a feature.
- **Terminal:** Font 14–16pt, clear history.
- **Chapters:** Paste timestamps in the YouTube description.
- **Thumbnail:** Search results UI + text like “YouTube → Track DNA → Vector Search | Local Docker”
- **Legal / framing (spoken + description):** Personal/portfolio demo. Analyze to build vectors; **audio deleted after ingest**. Respect YouTube ToS; do not redistribute downloaded audio; not affiliated with YouTube/Google. Prefer showing UI/results over playing full tracks in the video.

---

## Suggested Title Options

- "I Built a Local AI That Listens to YouTube Techno and Finds Similar Tracks"
- "Track DNA: Audio Embeddings + Vector Search for Electronic Music (Docker Compose)"
- "No Spotify API — YouTube URL In, Semantic Music Search Out"
- "CLAP + Qdrant + Airflow: Content-Based DJ Search on My Laptop"
- "Vectors Not MP3s: Local Track DNA Search with Airflow + Qdrant"

---

## YouTube Description Template

```
I built a fully local “Track DNA” system for electronic music: paste YouTube URLs, analyze the real audio, store dual vectors in Qdrant, and search by text or by similar sound — orchestrated with Airflow, served by FastAPI + Streamlit.

No cloud LLM required. CLAP for audio similarity, MiniLM for free-text search, template-based Track DNA reports.
Downloaded audio is deleted after indexing — the library keeps vectors + DNA reports, not a music archive.

WHAT'S COVERED:
- Architecture (Airflow, Qdrant named vectors, FastAPI, Streamlit)
- Full data flow: URL → download → features → sections → DNA → dual embed → reports → cleanup
- Resilient batch ingest (skip bad URLs; capped download concurrency)
- Live ingest demo
- Free-text, similar-to-YouTube, and refined similarity search
- Code walkthrough
- How I'd scale this with unlimited resources (models, hybrid search, K8s/Kafka, eval loop)

TECH STACK:
- Docker Compose
- Apache Airflow (TaskFlow, mapped tasks)
- Qdrant (audio 512-d + text 384-d named vectors)
- CLAP (laion/larger_clap_music_and_speech)
- sentence-transformers (all-MiniLM-L6-v2)
- yt-dlp, ffmpeg, librosa
- FastAPI, Streamlit
- Python 3.11

TIMESTAMPS:
0:00 — Hook (search demo)
1:30 — Architecture
4:00 — Data flow URL → Qdrant → cleanup
9:00 — Three search modes
12:30 — Code walkthrough
16:00 — Live ingest
19:30 — Design tradeoffs
22:00 — Next level (vision & scale, 6–7 min)
28:30 — How to run it

DISCLAIMER:
Personal/portfolio project. Not affiliated with YouTube. Respect platform terms and copyright; do not use this to redistribute music.

GitHub: [YOUR REPO LINK HERE]

#DataEngineering #VectorSearch #Qdrant #Airflow #AudioML #CLAP #Portfolio #Docker #ElectronicMusic
```

---

## Checklist Before Recording

- [ ] `docker compose ps` — postgres, qdrant, airflow-*, api, ui healthy (no ollama)
- [ ] `track_dna_dag` unpaused; at least one successful DAG run including `cleanup_audio`
- [ ] ~10–16 tracks already in Qdrant (warm HF cache); free-text search returns ranked hits
- [ ] After ingest, `data/raw_audio` and `data/wav` are empty (or nearly); `data/reports/` has `.md` files
- [ ] Streamlit http://localhost:8501 — Ingest / Search / Library work
- [ ] Airflow http://localhost:8080 (admin/admin)
- [ ] FastAPI http://localhost:8000/docs — `/search/text` vs `/search/similar` clear
- [ ] Qdrant http://localhost:6333/dashboard
- [ ] VS Code: `dags/track_dna_dag.py`, `src/downloader.py`, `src/embeddings.py`, `src/search.py` ready
- [ ] Sample `data/reports/*.md` ready to open
- [ ] Backup YouTube URLs for live ingest + similar search (clean `watch?v=` links)
- [ ] Terminal clean, font 14+, notifications off
- [ ] Design diagram (`docs/design.md`) ready to show on screen
- [ ] Talking points ready: skip-on-error, concurrency=3, delete-audio-after-index, personal demo framing
- [ ] Optional roadmap slide for Chapter 8 (Models → Product → Platform → Evaluation)
- [ ] Estimated recording: 25–32 min (record extra, cut later)
