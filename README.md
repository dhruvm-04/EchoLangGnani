# EchoLang

EchoLang is a voice-first local services directory. Customers describe the help they need and hear matching providers. Providers answer spoken questions to create an entry, review it before publication, and later update, pause, or delete it. Directory entries and drafts live in a local SQLite database. The app supports Bengali, English, Gujarati, Hindi, Kannada, Malayalam, Marathi, Punjabi, Tamil, and Telugu; choosing a language changes both the interface and the speech flow.

## Deploy on Render (free web service)

The root `render.yaml` deploys a single Docker web service. Its build compiles the React app, then FastAPI serves the app and `/api` from one HTTPS origin. The presentation is at `/presentation.html`.

1. Push this repository to GitHub. Keep `backend/.env` out of Git; it is ignored, and the Docker build excludes it.
2. In Render, select **New → Blueprint**, connect the GitHub repository, and approve the `render.yaml` Blueprint.
3. Enter `GNANI_API_KEY` and `ECHOLANG_LLM_API_KEY` when Render requests the two secret values. Use the Gnani key with STT/TTS access and your Groq API key. The Blueprint already sets Groq's base URL and `openai/gpt-oss-120b` model.
4. Wait for the Docker build and deploy. Open the assigned `https://…onrender.com` URL. Check `/api/health`: `gnaniKeyConfigured` and `reasoningConfigured` should both be `true`. Open the app on a phone and allow microphone access when prompted.

If you created the service before adding the Blueprint secrets, enter both keys under **Environment** in the Render dashboard and redeploy. Never put keys in frontend variables or Git. For live logs and failures, use the Render service's **Logs** tab. To protect a pilot with real listings, set `ECHOLANG_REQUIRE_APPROVAL=1` and a strong `ECHOLANG_ADMIN_KEY` in Render; the operator view is at `/?operator=1`.

**Free-tier data limit:** This deployment keeps SQLite at `/tmp/echolang.sqlite3`. Render's free web service sleeps after inactivity and its local files are lost on spin-down, restart, or redeploy. Provider listings, drafts, reports, and metrics therefore reset. Create a fresh demo listing after each wake, or use a paid persistent disk or an external database before collecting real provider data. A free web service also has a cold-start delay. The public demo can consume Gnani and Groq credits; monitor both dashboards and limit who receives the URL if needed. Do not treat this setup as durable storage for real providers.

To test the production image locally, run `docker build -t echolang .`, then `docker run --rm -p 10000:10000 -e GNANI_API_KEY=... -e ECHOLANG_LLM_API_KEY=... -e ECHOLANG_LLM_BASE_URL=https://api.groq.com/openai/v1 -e ECHOLANG_LLM_MODEL=openai/gpt-oss-120b echolang`. Open `http://localhost:10000` for a basic check. Browser microphone capture on a phone requires the deployed HTTPS address.

### Show EchoLang at `/echolang/` on a Vercel portfolio

Keep the portfolio domain pointed at Vercel. In the **portfolio project's** `vercel.json`, merge these rules with any existing redirects or rewrites. Replace `YOUR-RENDER-SERVICE.onrender.com` with the actual Render hostname, then redeploy the portfolio:

```json
{
  "redirects": [
    { "source": "/echolang", "destination": "/echolang/", "permanent": true }
  ],
  "rewrites": [
    { "source": "/echolang/:path*", "destination": "https://YOUR-RENDER-SERVICE.onrender.com/:path*" }
  ]
}
```

The trailing slash matters for relative frontend assets. The app uses relative asset, API, and home links, so Vercel can forward `/echolang/`, `/echolang/assets/…`, and `/echolang/api/…` to the same Render service. No DNS change or Render custom domain is needed for this path. Test `/echolang/` and `/echolang/api/health` on the portfolio domain after the portfolio deployment. The site's current root-to-`www` redirect may make the visible URL `www.dhruvmaheshwari.in/echolang/`.

## Run locally

Use Python 3.11 or 3.12 and Node.js 20 or newer. From this folder, in PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
# Edit backend/.env with your own speech and reasoning API credentials.
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --reload
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The backend health endpoint is at http://127.0.0.1:8000/api/health. API documentation is at http://127.0.0.1:8000/docs. The interface shows when speech or reasoning is not configured. API keys stay in the backend environment. Gnani handles speech recognition and synthesis; an OpenAI-compatible `/chat/completions` endpoint handles interpretation and localized replies. These services process spoken content, so obtain consent before using real personal details.

To open the interface on a phone connected to the same Wi-Fi, run `npm run dev:lan` in `frontend` and open `http://<computer-Wi-Fi-IP>:5173` on the phone. The backend can stay on `127.0.0.1:8000` because Vite proxies `/api` requests. Allow Node.js through Windows Firewall for the active network profile if the phone cannot reach the page. A LAN HTTP address does not provide the secure context required for browser microphone access; use an HTTPS address for the voice flows on a phone.

The frontend proxies `/api` to port 8000 in local development. To use different frontend origins, set `ECHOLANG_CORS_ORIGINS` as a comma-separated list. The local database defaults to `backend/data/echolang.sqlite3`; set `ECHOLANG_DB_PATH` to place it elsewhere. The database, backups, `.env`, dependencies, and build output are excluded from Git.

## Use the directory

On first visit, choose one of the ten language buttons. **Find help** asks for a service and city or area, confirms the request, searches local entries, and reads a provider aloud. A customer can say **next**, **previous**, **repeat**, or **new search**, or use the matching buttons. A call button opens the phone dialer. Optional spoken availability and provider-language preferences narrow results. No external directory is queried.

**Offer a service** starts a question-by-question voice flow. The provider reviews the draft and chooses to publish. A private owner token is saved in that browser for later edits, pause, or deletion. Anyone with the token or a recovery link can control the listing, so share recovery links privately. Audio recordings are not stored by the app; listing details, including the public phone number, are stored locally.

For a pilot with real providers, set `ECHOLANG_REQUIRE_APPROVAL=1` and a strong `ECHOLANG_ADMIN_KEY`. Then submissions wait for an operator to call the provider and approve them at `/?operator=1`. The operator can review reports, hide listings, locate a provider by phone, and issue a new access link after a callback. A new link revokes the previous owner token. The app does not automatically verify phone ownership or whether a job was completed. See [pilot priorities](docs/pilot-research-and-measures.md).

## Checks and backups

Run the automated checks from the project root:

```powershell
$env:PYTHONPATH='backend'
backend/.venv/Scripts/python -m unittest discover -s backend/tests -v
cd frontend
npm run build
```

The browser QA scripts (`npm run qa:languages`, `qa:live`, `qa:visual`) need a running frontend and Microsoft Edge/Playwright. Live speech checks need configured credentials and are separate from the automated tests: `backend/scripts/check_gnani.py`, `check_reasoning.py`, `smoke.py` (with consented WAV samples), and `synthetic_matrix.py`.

Create a consistent database backup with:

```powershell
$env:PYTHONPATH='backend'
backend/.venv/Scripts/python backend/scripts/backup_directory.py
```

Backups default to `backend/data/backups/` and contain provider contact details. Protect them and test restoration before collecting real listings. The backend, frontend, and tests can be run from a fresh clone without the current machine's database or credentials; live voice features require your own configured API access.
