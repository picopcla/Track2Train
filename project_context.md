# 🎯 Handover Context: Track2Train v2.15

This document preserves the state, architecture, and recent evolution of the Track2Train dashboard for continuity across AI sessions.

## 🏗️ Project Architecture
- **Core**: Flask application (`app.py`) serving a running dashboard.
- **Frontend**: Single-page dynamic dashboard (`templates/index.html`) using **Jinja2**, **ApexCharts**, and **Chart.js**.
- **AI Engine**: Google Gemini 1.5 (`google-genai`) for coaching comments and weekly planning.
- **Data**: Local JSON storage (`activities.json`, `profile.json`, `running_stats.json`).

## 🚀 Recent Evolutions (v2.15)
- **UTF-8 Restoration**: Fully stabilized character encoding (fixed mojibake for French accents and emojis).
- **Unified Versioning**: Single source of truth in `VERSION` file, dynamically linked to header and footer.
- **Enhanced Visuals**: 
    - Smooth brown elevation profiles with dynamic Y-axis.
    - Right-aligned pace charts with integrated HR data.
    - Bullet charts for efficiency markers (k) and cardiac drift.
- **AI Coaching v3**: Transitioned to strict plain-text coaching outputs for dashboard stability.

## 🔐 Security & Environment
- **Local (Windows)**: Credentials stored in `C:\StravaSecurity\`.
- **VM (Linux)**: Path mapped to `/opt/app/Track2TrainSecurity/`.
- **Environment**: Critical variables (`OPENAI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, `FOLDER_ID`) must be defined in a local `.env` file (which is ignored by Git).

## 🔄 Deployment Workflow (NEW)
We have shifted from manual file copying to a **Git-based synchronization**:
1. **Repository**: Local project is a Git repo (v2.15 initialized).
2. **Exclusion Rules**: `.gitignore` strictly prevents transferring `venv/` or `.env` between Windows and Linux.
3. **VM Setup**: Requires a Linux-specific virtual environment (`python3 -m venv venv`) and `pip install -r requirements.txt`.

## 🛠️ Maintenance Tools
- **`standardized_repair.py`**: A master script to fix visualization blocks in `index.html` if they become corrupted during edits. Always use `v2.15_final` as the gold standard.
- **`calculate_running_stats.py`**: Logic for k-factor, drift, and performance classification.

## 📋 Ongoing & Future Tasks
- [ ] Connect local Git repo to a private remote (GitHub/GitLab).
- [ ] Refine "Race Mode" detection in AI planning.
- [ ] Standardize mobile responsiveness for new chart layouts.

---
**Current State**: Stable v2.15. Port 5002.
**Last Backup**: `templates/index_v2.15_final.html`
