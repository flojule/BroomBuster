# Web Hosting — Options and Rationale

BroomBuster needs to host a Python backend (FastAPI) and a small static frontend (one HTML file plus icons). The backend is the constraint: it needs to run a Docker container with geopandas and enough RAM to keep city GeoDataFrames in memory (~200 MB for the Bay Area region).

---

## Current choice: Render.com (free tier)

The Docker container is deployed to Render as a free web service. The frontend is served as static files by FastAPI itself (no separate hosting needed).

**Pros:**
- Free. No credit card required for the free tier.
- Native Docker support — the Dockerfile matches the local dev environment exactly.
- Automatic deploys on git push.
- Provides a stable HTTPS URL, required for PWA install and geolocation on iPhone.
- Health check path (`/health`) supported out of the box.

**Cons:**
- Spins the container down after 15 minutes of inactivity. Cold start takes 20-40 s (Python + geopandas import + GeoDataFrame load).
- 512 MB RAM limit. Both region GDFs combined are ~200 MB, leaving ~300 MB for the rest of the process. This is sufficient but tight.
- Shared CPU — request latency is variable.
- Free plan no longer available for new signups as of late 2024 (existing free services continue to work; new projects must use the $7/mo Starter plan).

**The spin-down behavior** is the most visible limitation. UptimeRobot (free, 5-minute ping interval) can keep the container warm during active use, but it will still cold-start if no traffic arrives for 15+ minutes. This is acceptable for a prototype.

**Verdict**: the right choice while the project is a prototype with low traffic. Move to a paid tier or an alternative once it has regular users.

---

## Alternative: Fly.io (free tier)

Fly.io runs Docker containers on dedicated micro VMs. The free tier includes 3 shared-CPU VMs (256 MB RAM each) or 1 VM with up to 1 GB RAM.

**Pros:**
- Containers do not spin down the same way Render does — the VM can be configured to auto-suspend on idle and resume in 1-2 s (much faster than Render's cold start).
- 1 GB RAM available on the free tier, which comfortably fits all city GDFs.
- Good CLI tooling (`flyctl`).
- No build-minutes cap.

**Cons:**
- Free tier requires a credit card on file (not charged unless you exceed limits).
- More configuration required than Render (no automatic git-push deploys without extra setup).
- The 1 GB RAM VM is only free for one machine; adding more requires payment.

**Verdict**: a strong alternative to Render if the spin-down latency becomes a real problem. The credit card requirement and extra setup are the main barriers for a prototype.

---

## Alternative: Railway (free tier)

Railway runs Docker containers with a $5/month free credit (as of 2024).

**Pros:**
- $5/month credit covers low-traffic usage (roughly 500 hours of a 1 vCPU / 512 MB instance).
- Automatic git-push deploys.
- Simple UI, easy to set environment variables.
- No spin-down like Render.

**Cons:**
- The free credit runs out if the container runs 24/7 (~$5 for ~500 hours, which is roughly 20 days of continuous uptime). Scaling down to run only when needed extends this.
- Requires a credit card.
- Less community documentation than Render or Fly.io.

**Verdict**: viable, but the credit-based model makes the "free" tier less predictable than Render or Fly.io for a prototype.

---

## Alternative: Vercel or Netlify (frontend only) + separate backend

Deploy the static frontend (`index.html`, `manifest.json`, `sw.js`) to Vercel or Netlify, and host the Python backend separately (Render, Fly.io, etc.).

**Pros:**
- Vercel and Netlify are excellent for static sites: global CDN, instant deploys, custom domains on free tier.
- The frontend loads from a fast CDN edge node instead of the same origin as the API.

**Cons:**
- Two services to manage and keep in sync.
- CORS configuration required on the backend (currently set to `allow_origins=["*"]`).
- The frontend is a single 300-line HTML file — the CDN benefit is minimal compared to serving it from the same Render origin.

**Verdict**: not worth the added complexity for this prototype. Revisit if the frontend grows into a proper build-step app (React, etc.) or if CDN performance becomes a concern.

---

## Alternative: GitHub Pages (frontend only)

Host the static frontend on GitHub Pages, pointing the API calls to the Render backend.

**Pros:**
- Completely free, no account needed beyond GitHub.
- Automatic deploy from the repo on push.

**Cons:**
- Same split-service drawbacks as Vercel/Netlify above.
- No server-side rendering or backend logic.
- GitHub Pages serves from a `github.io` domain by default; custom domain requires DNS setup.

**Verdict**: same as Vercel/Netlify — not worth the split for a single-file frontend.
