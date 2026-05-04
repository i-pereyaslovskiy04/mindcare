# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MindCare is a monorepo with two sub-projects:
- `mindcare_api/` — Python FastAPI backend, runs on port 8000
- `mindcare_web/` — React 19 frontend (Create React App), runs on port 3000

## Commands

### Backend (`mindcare_api/`)
```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload
```

### Frontend (`mindcare_web/`)
```bash
# Install dependencies
npm install

# Start dev server
npm start

# Build for production
npm run build

# Run all tests
npm test

# Run a single test file
npm test -- --testPathPattern=App.test.js
```

## Architecture

### API ↔ Frontend Proxy
`mindcare_web/package.json` sets `"proxy": "http://localhost:8000"`, so all `fetch("/api/...")` calls in the React app are forwarded to the FastAPI backend during development. Both servers must be running for full-stack local dev.

### Frontend Structure
The `src/` folder follows a feature-based layout (most are stubs, being built out):
- `api/api.js` — centralized API client (all `fetch` calls go here)
- `features/` — feature slices (e.g., `auth/`)
- `pages/` — route-level page components, each with a co-located `.module.css`
- `routes/AppRoutes.jsx` — React Router route definitions
- `store/store.js` — global state (Redux or Context, not yet implemented)
- `styles/theme.js` + `styles/global.css` — design tokens and baseline styles

### Backend Structure
The API lives entirely in `app/main.py` as a single FastAPI app instance. Routes use the `/api/` prefix to match the frontend proxy configuration.
