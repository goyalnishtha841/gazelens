# GazeLens Studio frontend

An independent dark visual alternative to `frontend-new`, using the same backend and application behavior. The landing page uses a luminous lens, violet/blue/pink accents, and a scroll-driven transition into an illustrative report. Reduced-motion preferences show the hero and preview in normal flow.

```powershell
cd frontend-studio
npm ci
npm run dev
```

Open http://localhost:5181. Keep the API running on port 8000. The original frontend remains at http://localhost:5180 when run from `frontend-new`.

The API calls, authentication, session state, data handling, gaze processing, and report components are copied unchanged. Presentation changes are in `src/studio.css`, the landing page, the auth layout, and a decorative report preview. A wrapper preserves the original calibration palette. No backend files are changed.

Both frontends use the same browser storage keys and API. Existing server data is shared; calibration is still checked against the current window dimensions.

The report preview on the landing page is illustrative, not a recorded session.
