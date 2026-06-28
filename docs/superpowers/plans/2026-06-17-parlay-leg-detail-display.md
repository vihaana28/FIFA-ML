# Parlay Leg Detail Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show exact pick details for all displayed parlays.

**Architecture:** Add pure formatting helpers in `frontend/src/betting.ts`, test them in `frontend/src/__tests__/betting.test.ts`, then replace the parlay-card leg rendering in `frontend/src/App.tsx` with those helpers. No backend change is needed because the API already sends the data.

**Tech Stack:** React, TypeScript, Vite, Vitest.

---

### Task 1: Parlay Leg Formatting

**Files:**
- Modify: `frontend/src/betting.ts`
- Modify: `frontend/src/__tests__/betting.test.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write failing tests**

Add tests for a moneyline leg label and nested parlay flattening.

- [ ] **Step 2: Run test to verify red**

Run: `cd frontend; npm test -- src/__tests__/betting.test.ts`

Expected: FAIL because helper exports do not exist yet.

- [ ] **Step 3: Implement helper**

Add `recommendedParlayLegDetails` and `recommendedParlayPickLines` to `frontend/src/betting.ts`.

- [ ] **Step 4: Render helper output**

Use `recommendedParlayPickLines` for selected-game parlay and best-parlay-by-day cards in `frontend/src/App.tsx`.

- [ ] **Step 5: Verify**

Run:

```powershell
npm test
npm run build
```
