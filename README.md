# EchoLang

· [Try the live demo here](https://www.dhruvmaheshwari.in/echolang/)\
· [Read the one-page solution pitch](SOLUTION_PITCH.pdf)\
· [View the presentation](presentation.html)

EchoLang is a local services directory designed for smaller Indian cities and towns, including tier-2 and tier-3 areas. The search flow uses basic phone actions: choose a language, speak a need and place, confirm what the app heard, and listen to local matches. It is intended for people who can use a phone but are less comfortable with search terms or long forms. Workers can create and manage listings through short voice or text prompts.

The directory searches its own SQLite listings. The demo starts with 200 fictional providers across 88 Indian cities and 31 service types, so you can try a search immediately. It does not pull results from Google or another service.

## What the demo includes

- A voice and text path for finding help or offering a service.
- Interfaces and spoken replies in Bengali, English, Gujarati, Hindi, Kannada, Malayalam, Marathi, Punjabi, Tamil, and Telugu. The language picker appears after the intro on every page load.
- A review step before a worker publishes a listing, plus controls to edit, pause, or delete it later.
- Clearly named demo listings with placeholder numbers. They are examples, not real people to call.
- An operator page for reviewing submissions and reports.
- An [HTML presentation](presentation.html) for the pitch. Use the left and right arrow keys to move through its six slides.

The frontend is React and TypeScript. FastAPI handles the conversation and directory API, and SQLite stores listings. Gnani handles speech recognition and speech synthesis. A Groq-hosted GPT-OSS model interprets requests and helps write replies.

## Run it locally

You need Python 3.11 or 3.12 and Node.js 20 or newer. These commands are for PowerShell, starting in the repository root.

First, copy the backend environment file and add your own Gnani and Groq API keys:

```powershell
Copy-Item backend/.env.example backend/.env
```

Set `GNANI_API_KEY` and `ECHOLANG_LLM_API_KEY` in `backend/.env`. The example file already contains the model names and Groq URL used by the demo. Keep that file private.

The example file also sets `ECHOLANG_SEED_DEMO=1`, which adds sample listings when the API starts.

Start the API:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --reload
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Vite sends `/api` requests to the local FastAPI server on port 8000. The [presentation](http://127.0.0.1:8000/presentation.html), [health check](http://127.0.0.1:8000/api/health), and [API documentation](http://127.0.0.1:8000/docs) are served by that backend.

The app shows a text input if the microphone is unavailable. For voice input on a phone, use an HTTPS deployment; a plain HTTP address on your local network will not give the browser microphone access.

If you already have a `backend/.env` file without the demo setting, add `ECHOLANG_SEED_DEMO=1` and restart the API. You can also seed the current database without restarting, from the repository root:

```powershell
$env:PYTHONPATH='backend'
backend/.venv/Scripts/python backend/scripts/seed_demo.py
```

Running the command again will not create duplicates. It also removes old demo entries that are no longer in the seed set; real provider entries are left alone.
