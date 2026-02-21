# R10 TODO
**Created:** February 20, 2026  
**Spec:** docs/R10-Architecture-Spec.md  
**Status:** Planning

---

## IMMEDIATE — Before Any Code Changes

- [ ] Revert docker-compose.yml to pre-session state (remove Neo4j additions made in error)
- [ ] Corpus audit — get accurate conversation/message/token counts from database
- [ ] Triage broken conversations (message_count > 0 but viewer fails to open)
- [ ] Review Troubadourian Amphitheatre (Cowork report pending)
- [ ] Graph infrastructure decision (post-Troubadourian review)

---

## R10 CORE — Multi-App Architecture

- [ ] Create main.py (gr.routes() mount point + session persona)
- [ ] Extract app_projects.py from current app.py (no UI changes)
- [ ] Create app_atlas.py (Knowledge/ATLAS refactor)
- [ ] Create app_chat.py (three-panel continuous chat)
- [ ] Wire app_admin.py into routes
- [ ] Test persona persistence across app navigation

---

## R10 — ATLAS / Knowledge Refactor

- [ ] Fix conversation counter bug (shows 0 conversations / 0 messages)
- [ ] Remove raw ID column, replace with short hash
- [ ] Add Est. Tokens column to Conversations tab
- [ ] Add Status column (✓ content / ⚠ empty / ✗ broken)
- [ ] Merge Documents + List View into single Corpus tab
- [ ] Remove Search tab, move to sidebar search bar
- [ ] Build Corpus Stats Panel (persistent left sidebar across all Knowledge tabs)
- [ ] Stub Connections tab as read-only Triad Visualization placeholder

---

## R10 — Chat Refactor

- [ ] Remove chat list from left sidebar
- [ ] Build Instrument Panel (left — retrieval transparency, user-only)
- [ ] Build temporal affinity tracker and display
- [ ] Wire shaping parameters (recency bias, depth) to persona
- [ ] Verify right panel session settings apply per-turn
- [ ] Confirm Janus never receives left panel content in context

---

## DEFERRED — Post-R10

- [ ] Graph schema design session (requires Troubadourian Amphitheatre review)
- [ ] Graph store selection (Neo4j vs FalkorDB vs AGE)
- [ ] Graph store container integration
- [ ] graph_service.py in ATLAS module
- [ ] Cross-reference IDs between SQL, Vector, Graph
- [ ] Connections tab full Triad visualization
- [ ] Embedding pipeline for pending corpus (116 unembedded, count TBD after audit)
- [ ] Accurate token counting pipeline
