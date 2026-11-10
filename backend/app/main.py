from __future__ import annotations

import base64
import hmac
import io
import json
import os
import wave
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .adapters import GnaniClient, ServiceError
from .core import LANGUAGES, State, confirmation, decide, state_dict
from .directory import DirectoryStore, FIELDS, QUESTIONS, REQUIRED, clean, phone_digits
from .reasoning import MultilingualReasoner

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="EchoLang API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("ECHOLANG_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.state.gnani = GnaniClient()
app.state.reasoner = MultilingualReasoner()
app.state.store = DirectoryStore()


@app.exception_handler(ServiceError)
async def service_error_handler(_, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"error": exc.code, "message": str(exc)})


@app.get("/api/health")
async def health():
    return {"status": "ok", "gnaniKeyConfigured": bool(app.state.gnani.key), "reasoningConfigured": app.state.reasoner.configured, "directory": "local"}


@app.get("/api/config")
async def config():
    return {
        "languages": [{"code": code, "name": values[0]} for code, values in LANGUAGES.items()],
        "sttModel": app.state.gnani.stt_model,
        "ttsModel": app.state.gnani.tts_model,
        "requiresLanguageSelection": app.state.gnani.stt_model == "prisma-v2.5",
        "gnaniKeyConfigured": bool(app.state.gnani.key),
        "reasoningConfigured": app.state.reasoner.configured,
        "directory": "local",
    }


def _wav_duration(audio: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio), "rb") as sound:
            if sound.getnchannels() != 1 or sound.getsampwidth() != 2:
                raise ValueError("WAV must be mono 16-bit PCM")
            return sound.getnframes() / sound.getframerate()
    except (wave.Error, ValueError, ZeroDivisionError) as exc:
        raise ServiceError("Record again. The audio must be a valid mono WAV file.", 400, "invalid_audio") from exc


def _result_reply(matches: list[dict], state: State, action: str = "initial") -> str:
    if not matches:
        details = []
        if state.availability:
            details.append(f"confirmed for {state.availability}")
        if state.preferred_language:
            details.append(f"speaking {state.preferred_language}")
        qualifier = " " + " and ".join(details) if details else ""
        return f"I found no local {state.category} providers in {state.location}{qualifier}. Say another service or area to search again."
    if action == "next":
        state.result_index = min(state.result_index + 1, len(matches) - 1)
    elif action == "previous":
        state.result_index = max(state.result_index - 1, 0)
    state.result_index = min(state.result_index, len(matches) - 1)
    provider = matches[state.result_index]
    intro = (f"I found {len(matches)} local providers. " if action == "initial" else
             "That is the last provider. " if action == "next" and state.result_index == len(matches) - 1 and len(matches) > 1 else
             "That is the first provider. " if action == "previous" and state.result_index == 0 else "")
    if action == "call":
        intro = f"Tap Call provider to contact {provider['name']}. "
    details = [f"Provider {state.result_index + 1} of {len(matches)}: {provider['name']}.",
               f"Offers {', '.join(provider['services'])} in {provider['area']}.", provider["delivery"] + "."]
    if provider["hours"]:
        details.append(f"Hours: {provider['hours']}.")
    if provider["languages"]:
        details.append(f"Languages: {provider['languages']}.")
    if provider["price"]:
        details.append(f"Price: {provider['price']}.")
    details.append("Say next, previous, or repeat. Tap Call provider to contact them.")
    return intro + " ".join(details)


@app.post("/api/turn")
async def turn(
    audio: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    control: str | None = Form(default=None),
    state: str = Form(default="{}"),
    selected_language: str | None = Form(default=None),
    location_override: str | None = Form(default=None),
):
    try:
        parsed_state = State.from_dict(json.loads(state))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid conversation state") from exc
    if selected_language and selected_language not in LANGUAGES:
        raise ServiceError("Choose one of the listed languages.", 400, "invalid_language")
    if location_override and location_override.strip():
        parsed_state.location = location_override.strip()[:100]
    if selected_language:
        parsed_state.language = selected_language

    if control in {"yes", "no", "next", "previous", "repeat", "new_search", "call"}:
        transcript, detected_language, stt_used = control, "en-IN", None
    elif control is not None:
        raise ServiceError("Choose a listed control.", 400, "invalid_control")
    elif audio is not None:
        content = await audio.read(12_000_001)
        if len(content) > 12_000_000:
            raise ServiceError("Audio is too large. Keep recordings under 30 seconds.", 413, "audio_too_large")
        duration = _wav_duration(content)
        if duration < 0.1 or duration > 30:
            raise ServiceError("Record between 0.1 and 30 seconds.", 400, "audio_length")
        transcript, detected_language, stt_used = await app.state.gnani.transcribe(content, selected_language or parsed_state.language)
    elif text and text.strip():
        transcript = text.strip()[:500]
        if not transcript.isascii() and not (selected_language or parsed_state.language):
            raise ServiceError("Choose a language for typed text.", 400, "language_selection_required")
        detected_language = (selected_language or parsed_state.language or "en-IN") if not transcript.isascii() else "en-IN"
        stt_used = None
    else:
        raise ServiceError("Record your request or type it below.", 400, "missing_input")

    response_language = parsed_state.language or detected_language
    navigation = None
    if parsed_state.phase == "done":
        navigation = control if control in {"next", "previous", "repeat", "new_search", "call"} else None
        if navigation is None and not control:
            navigation = await app.state.reasoner.navigate_results(transcript, detected_language)
    if navigation in {"next", "previous", "repeat", "call"}:
        next_state = parsed_state
        matches = app.state.store.search(next_state.category or "", next_state.location,
                                         availability=next_state.availability, language=next_state.preferred_language)
        english_reply = _result_reply(matches, next_state, navigation)
        english = transcript
    elif navigation == "new_search":
        next_state = State(language=response_language)
        matches = []
        english_reply = "Tell me the service and city or area you need."
        english = transcript
    else:
        if parsed_state.phase == "done":
            parsed_state = State(language=response_language)
        if control:
            parsed = {"english_request": transcript, "service": None, "location": None, "alternative": None,
                      "answer": transcript, "availability": None, "preferred_language": None}
        else:
            parsed = await app.state.reasoner.interpret(transcript, detected_language, parsed_state.phase)
        english = parsed["english_request"]
        if parsed_state.phase == "awaiting_confirmation" and parsed["answer"]:
            english = parsed["answer"]
        category = parsed["service"] if parsed_state.phase == "new" else None
        alternative = parsed["alternative"] if category else None
        next_state, english_reply = decide(
            parsed_state, english, response_language,
            category, alternative, parsed["location"],
        )
        if next_state.phase in {"awaiting_location", "awaiting_confirmation", "done"}:
            next_state.availability = parsed.get("availability") if parsed_state.phase == "new" else parsed_state.availability
            next_state.preferred_language = parsed.get("preferred_language") if parsed_state.phase == "new" else parsed_state.preferred_language
        matches = []
        if next_state.phase == "done" and next_state.category:
            matches = app.state.store.search(next_state.category, next_state.location,
                                             availability=next_state.availability, language=next_state.preferred_language)
            english_reply = _result_reply(matches, next_state)
    localized_reply = await app.state.reasoner.localize(english_reply, response_language)
    if next_state.phase == "done" and parsed_state.phase != "done":
        app.state.store.record_event("search_with_results" if matches else "search_without_results")

    speech = None
    speech_warning = None
    try:
        speech = base64.b64encode(await app.state.gnani.synthesize(localized_reply, response_language)).decode("ascii")
    except ServiceError as exc:
        speech_warning = str(exc)

    return {
        "transcript": transcript,
        "detectedLanguage": detected_language,
        "englishTranscript": english,
        "replyText": localized_reply,
        "replyEnglish": english_reply,
        "replyAudioBase64": speech,
        "speechWarning": speech_warning,
        "state": state_dict(next_state),
        "category": next_state.category,
        "location": next_state.location,
        "confidence": None,
        "matches": matches,
        "activeIndex": next_state.result_index if matches else None,
        "modelsUsed": [name for name in [stt_used, app.state.reasoner.model if not control or response_language != "en-IN" else None, app.state.gnani.tts_model if speech else None] if name],
    }


class StartProvider(BaseModel):
    language: str = "en-IN"
    prompt_language: str | None = None


class ListingUpdate(BaseModel):
    field: str
    value: str
    language: str | None = None


class ListingReport(BaseModel):
    reason: str


class StatusUpdate(BaseModel):
    status: str


class ReportResolution(BaseModel):
    resolution: str


class DeleteConfirmation(BaseModel):
    confirmation: str


async def _provider_input(audio: UploadFile | None, text: str | None, control: str | None, language: str) -> tuple[str, str, str | None]:
    if control:
        return control, language if language != "auto" else "en-IN", None
    if audio:
        content = await audio.read(12_000_001)
        if len(content) > 12_000_000 or not 0.1 <= _wav_duration(content) <= 30:
            raise ServiceError("Keep recordings under 30 seconds.", 400, "audio_length")
        return await app.state.gnani.transcribe(content, None if language == "auto" else language)
    if text and text.strip():
        return text.strip()[:500], language if language != "auto" else "en-IN", None
    raise ServiceError("Say your answer or type it.", 400, "missing_input")


async def _provider_reply(english: str, language: str) -> dict:
    if language == "auto":
        language = "en-IN"
    localized = await app.state.reasoner.localize(english, language)
    try:
        audio = base64.b64encode(await app.state.gnani.synthesize(localized, language)).decode("ascii")
    except ServiceError:
        audio = None
    return {"replyText": localized, "replyAudioBase64": audio}


def _draft_summary(fields: dict) -> str:
    details = [f"{fields.get('name', 'You')} offer {fields.get('services', 'services')} in {fields.get('area', 'your area')}.",
               f"Work arrangement: {fields.get('delivery', 'unspecified')}.",
               f"Contact number: {' '.join(phone_digits(fields.get('phone', '')))}."]
    for field, label in (("hours", "Hours"), ("languages", "Languages"), ("price", "Price")):
        if fields.get(field):
            details.append(f"{label}: {fields[field]}.")
    return " ".join(details) + " Publishing makes your name, service area, and phone number visible to people searching this directory. Do not include your home address. Say publish if you agree, or say what to change."


@app.post("/api/providers/start")
async def provider_start(request: StartProvider):
    if request.language != "auto" and request.language not in LANGUAGES:
        raise ServiceError("Choose a listed language.", 400, "invalid_language")
    if request.prompt_language and request.prompt_language not in LANGUAGES:
        raise ServiceError("Choose a listed prompt language.", 400, "invalid_language")
    draft = app.state.store.new_draft(request.language)
    app.state.store.record_event("provider_started")
    opening_language = request.prompt_language or (request.language if request.language != "auto" else "en-IN")
    return {"draftId": draft["id"], "fields": {}, "phase": "question", "field": FIELDS[0],
            **await _provider_reply(QUESTIONS[FIELDS[0]], opening_language)}


@app.get("/api/providers/drafts/{draft_id}")
async def provider_resume(draft_id: str, prompt_language: str | None = None, selected_language: str | None = None):
    draft = app.state.store.get_draft(draft_id)
    if not draft:
        raise ServiceError("This draft has expired. Please start again.", 404, "draft_not_found")
    if selected_language:
        if selected_language not in LANGUAGES:
            raise ServiceError("Choose a listed language.", 400, "invalid_language")
        draft["language"] = selected_language
        app.state.store.save_draft(draft)
    review = draft["cursor"] >= len(FIELDS)
    field = None if review else FIELDS[draft["cursor"]]
    prompt = _draft_summary(draft["fields"]) if review else QUESTIONS[field]
    language = draft["language"] if draft["language"] != "auto" else (prompt_language if prompt_language in LANGUAGES else "en-IN")
    return {"draftId": draft_id, "fields": draft["fields"], "phase": "review" if review else "question", "field": field,
            **await _provider_reply(prompt, language)}


@app.post("/api/providers/turn")
async def provider_turn(
    draft_id: str = Form(...), audio: UploadFile | None = File(default=None),
    text: str | None = Form(default=None), control: str | None = Form(default=None),
    selected_language: str | None = Form(default=None),
):
    draft = app.state.store.get_draft(draft_id)
    if not draft:
        raise ServiceError("This draft has expired. Please start again.", 404, "draft_not_found")
    if selected_language:
        if selected_language not in LANGUAGES:
            raise ServiceError("Choose a listed language.", 400, "invalid_language")
        draft["language"] = selected_language
        app.state.store.save_draft(draft)
    transcript, detected, model = await _provider_input(audio, text, control, draft["language"])
    if draft["language"] == "auto" and detected in LANGUAGES and detected != "en-IN":
        draft["language"] = detected
        app.state.store.save_draft(draft)
    fields = draft["fields"]
    if draft["cursor"] >= len(FIELDS):
        if control == "publish":
            command = {"action": "publish"}
        elif control and control.startswith("change:"):
            requested_field = control.removeprefix("change:")
            if requested_field not in FIELDS:
                raise ServiceError("Choose a valid listing detail.", 400, "invalid_field")
            command = {"action": "change", "field": requested_field}
        else:
            command = await app.state.reasoner.provider_command(transcript)
        if command["action"] == "publish":
            fields.pop("__review_field", None)
            try:
                approval = bool(os.getenv("ECHOLANG_ADMIN_KEY") and os.getenv("ECHOLANG_REQUIRE_APPROVAL") == "1")
                provider, token = app.state.store.publish(draft, approval)
            except ValueError as exc:
                code = "duplicate_listing" if "already has a listing" in str(exc) else "invalid_listing"
                raise ServiceError(str(exc), 400, code) from exc
            app.state.store.record_event("provider_published")
            message = "Your listing is saved and awaiting review." if approval else "Your listing is live in the local directory."
            return {"phase": "published", "provider": provider, "ownerToken": token, "transcript": transcript,
                    **await _provider_reply(message, draft["language"])}
        if command["action"] == "change" and command["field"] in FIELDS:
            field = command["field"]
            fields["__review_field"] = field
            draft["cursor"] = FIELDS.index(field)
            app.state.store.save_draft(draft)
            return {"draftId": draft_id, "fields": fields, "phase": "question", "field": field, "transcript": transcript,
                    **await _provider_reply(QUESTIONS[field], draft["language"])}
        return {"draftId": draft_id, "fields": fields, "phase": "review", "field": None, "transcript": transcript,
                **await _provider_reply("Please say publish, or say which detail to change.", draft["language"])}

    field = FIELDS[draft["cursor"]]
    if control == "skip":
        answer = {"value": "", "skip": True}
    else:
        answer = await app.state.reasoner.provider_answer(field, transcript)
    value = clean(answer["value"], 240)
    if answer["skip"] and field in REQUIRED:
        prompt = "This detail is needed for your listing. " + QUESTIONS[field]
    elif not value and not answer["skip"]:
        prompt = "I did not catch that. " + QUESTIONS[field]
    elif field == "phone" and not 10 <= len(phone_digits(value)) <= 15:
        prompt = "Please say a phone number with 10 to 15 digits. " + QUESTIONS[field]
    else:
        fields[field] = phone_digits(value) if field == "phone" else value
        if fields.get("__review_field") == field:
            fields.pop("__review_field", None)
            draft["cursor"] = len(FIELDS)
        else:
            draft["cursor"] += 1
        app.state.store.save_draft(draft)
        if draft["cursor"] >= len(FIELDS):
            return {"draftId": draft_id, "fields": fields, "phase": "review", "field": None, "transcript": transcript,
                    **await _provider_reply(_draft_summary(fields), draft["language"])}
        field = FIELDS[draft["cursor"]]
        prompt = QUESTIONS[field]
    return {"draftId": draft_id, "fields": fields, "phase": "question", "field": field, "transcript": transcript,
            "modelsUsed": [model] if model else [], **await _provider_reply(prompt, draft["language"])}


@app.get("/api/providers/me")
async def provider_me(authorization: str | None = Header(default=None)):
    provider = app.state.store.owner((authorization or "").removeprefix("Bearer "))
    if not provider:
        raise ServiceError("This device cannot access a provider listing.", 401, "owner_required")
    return provider


@app.post("/api/providers/me/status")
async def provider_status(update: StatusUpdate, authorization: str | None = Header(default=None)):
    provider = app.state.store.owner((authorization or "").removeprefix("Bearer "))
    if not provider:
        raise ServiceError("This device cannot access a provider listing.", 401, "owner_required")
    try:
        return app.state.store.owner_status(provider["id"], update.status)
    except ValueError as exc:
        raise ServiceError(str(exc), 400, "invalid_status") from exc


@app.post("/api/providers/me/delete")
async def provider_delete(request: DeleteConfirmation, authorization: str | None = Header(default=None)):
    provider = app.state.store.owner((authorization or "").removeprefix("Bearer "))
    if not provider:
        raise ServiceError("This device cannot access a provider listing.", 401, "owner_required")
    if request.confirmation != "delete":
        raise ServiceError("Confirm deletion first.", 400, "confirmation_required")
    app.state.store.delete_provider(provider["id"])
    return {"status": "deleted"}


@app.post("/api/providers/edit/prepare")
async def provider_edit_prepare(
    audio: UploadFile | None = File(default=None), text: str | None = Form(default=None),
    selected_language: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
):
    provider = app.state.store.owner((authorization or "").removeprefix("Bearer "))
    if not provider:
        raise ServiceError("This device cannot access a provider listing.", 401, "owner_required")
    language = selected_language if selected_language in LANGUAGES else "auto"
    transcript, language, _ = await _provider_input(audio, text, None, language)
    parsed = await app.state.reasoner.provider_edit(transcript)
    field, value = parsed["field"], clean(parsed["value"], 240)
    if field not in FIELDS or not value:
        return {"transcript": transcript, "field": None, "value": None,
                **await _provider_reply("Please say which listing detail to change and the new value.", language)}
    if field == "phone" and not 10 <= len(phone_digits(value)) <= 15:
        raise ServiceError("Please say a 10 to 15 digit phone number.", 400, "invalid_phone")
    if field == "services" and parsed.get("operation") == "add":
        value = ", ".join(dict.fromkeys([*provider["services"], value]))
    return {"transcript": transcript, "field": field, "value": value,
            **await _provider_reply(f"Change {field} to {value}? Say yes to save or no to cancel.", language)}


@app.post("/api/providers/edit/confirm")
async def provider_edit_confirm(update: ListingUpdate, authorization: str | None = Header(default=None)):
    provider = app.state.store.owner((authorization or "").removeprefix("Bearer "))
    if not provider:
        raise ServiceError("This device cannot access a provider listing.", 401, "owner_required")
    try:
        updated = app.state.store.update(provider["id"], update.field, update.value)
    except ValueError as exc:
        raise ServiceError(str(exc), 400, "invalid_listing") from exc
    language = update.language if update.language in LANGUAGES else "en-IN"
    return {"provider": updated, **await _provider_reply("Your listing has been updated.", language)}


@app.post("/api/providers/edit/answer")
async def provider_edit_answer(
    field: str = Form(...), value: str = Form(...), audio: UploadFile | None = File(default=None),
    text: str | None = Form(default=None), selected_language: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
):
    provider = app.state.store.owner((authorization or "").removeprefix("Bearer "))
    if not provider:
        raise ServiceError("This device cannot access a provider listing.", 401, "owner_required")
    transcript, language, _ = await _provider_input(audio, text, None, selected_language if selected_language in LANGUAGES else "auto")
    answer = confirmation(transcript)
    if answer is None:
        interpreted = await app.state.reasoner.interpret(transcript, language, "awaiting_confirmation")
        answer = confirmation(interpreted.get("answer") or "")
    if answer is True:
        try:
            updated = app.state.store.update(provider["id"], field, value)
        except ValueError as exc:
            raise ServiceError(str(exc), 400, "invalid_listing") from exc
        return {"saved": True, "provider": updated, "transcript": transcript,
                **await _provider_reply("Your listing has been updated.", language)}
    if answer is False:
        return {"saved": False, "cancelled": True, "transcript": transcript,
                **await _provider_reply("No change was saved.", language)}
    return {"saved": False, "cancelled": False, "transcript": transcript,
            **await _provider_reply("Please say yes to save or no to cancel.", language)}


@app.get("/api/directory/search")
async def directory_search(service: str, area: str = "", availability: str = "", language: str = ""):
    return {"matches": app.state.store.search(clean(service, 80), clean(area, 100),
                                               availability=clean(availability, 80), language=clean(language, 60))}


@app.post("/api/directory/{provider_id}/report")
async def directory_report(provider_id: str, report: ListingReport):
    if not report.reason.strip():
        raise ServiceError("Choose a reason.", 400, "invalid_report")
    try:
        app.state.store.report(provider_id, report.reason)
    except ValueError as exc:
        raise ServiceError(str(exc), 404, "listing_not_found") from exc
    app.state.store.record_event("listing_reported")
    return {"status": "received"}


@app.post("/api/directory/{provider_id}/contact")
async def directory_contact(provider_id: str):
    provider = app.state.store.get_provider(provider_id)
    if not provider or provider["status"] != "published":
        raise ServiceError("Listing not found.", 404, "listing_not_found")
    app.state.store.record_event("contact_tapped")
    return {"status": "recorded"}


def _admin(key: str | None) -> None:
    configured = os.getenv("ECHOLANG_ADMIN_KEY", "")
    if not configured or not key or not hmac.compare_digest(key, configured):
        raise ServiceError("Admin access required.", 403, "admin_required")


@app.get("/api/admin/pending")
async def admin_pending(x_admin_key: str | None = Header(default=None)):
    _admin(x_admin_key)
    return {"providers": app.state.store.pending()}


@app.get("/api/admin/providers/by-phone")
async def admin_provider_by_phone(phone: str, x_admin_key: str | None = Header(default=None)):
    _admin(x_admin_key)
    return {"providers": app.state.store.by_phone(phone)}


@app.get("/api/admin/reports")
async def admin_reports(x_admin_key: str | None = Header(default=None)):
    _admin(x_admin_key)
    return {"reports": app.state.store.reports()}


@app.get("/api/admin/metrics")
async def admin_metrics(x_admin_key: str | None = Header(default=None)):
    _admin(x_admin_key)
    return {"days": 30, "counts": app.state.store.metrics()}


@app.post("/api/admin/reports/{report_id}/resolve")
async def admin_resolve_report(report_id: int, update: ReportResolution, x_admin_key: str | None = Header(default=None)):
    _admin(x_admin_key)
    try:
        result = app.state.store.resolve_report(report_id, update.resolution)
    except ValueError as exc:
        raise ServiceError(str(exc), 400, "invalid_resolution") from exc
    if not result:
        raise ServiceError("Open report not found.", 404, "report_not_found")
    return result


@app.post("/api/admin/providers/{provider_id}/recover")
async def admin_recover_provider(provider_id: str, x_admin_key: str | None = Header(default=None)):
    _admin(x_admin_key)
    try:
        token = app.state.store.rotate_owner(provider_id)
    except ValueError as exc:
        raise ServiceError(str(exc), 404, "listing_not_found") from exc
    return {"ownerToken": token}


@app.post("/api/admin/providers/{provider_id}/status")
async def admin_status(provider_id: str, update: StatusUpdate, x_admin_key: str | None = Header(default=None)):
    _admin(x_admin_key)
    try:
        provider = app.state.store.set_status(provider_id, update.status)
    except ValueError as exc:
        raise ServiceError(str(exc), 400, "invalid_status") from exc
    if not provider:
        raise ServiceError("Listing not found.", 404, "listing_not_found")
    return provider
