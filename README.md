# InspireWorks IVR Demo (Plivo Voice API)

Outbound call → OTP authentication → Level 1 language menu → Level 2 action menu, built with Flask, the Plivo Python SDK and Plivo XML.

## Call flow

```
Outbound call (Plivo number → your phone)
  └─ /answer      "Enter your 4-digit OTP"   (GetDigits, 4 digits)
       ├─ wrong / no input → "incorrect" → back to /answer (loops until correct)
       └─ correct (1110, DDMM birthdate, hardcoded)
            └─ /language   "Press 1 English, 2 Español"
                 ├─ invalid → repeat prompt
                 └─ /menu?lang=en|es   (prompts spoken in the chosen language)
                      ├─ 1 → <Play> MP3 → goodbye → hangup
                      ├─ 2 → <Dial> live associate (+912264236412)
                      └─ invalid → repeat prompt
```

State is carried in the URL (`?lang=`), so there is no database or session store.

## Setup

Requires Python 3 and a way to expose localhost over HTTPS (ngrok or cloudflared).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then fill in the values below
```

`.env` values:

| Variable | Description |
|---|---|
| `PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN` | Plivo console → Overview |
| `PLIVO_NUMBER` | Caller ID / source number (`+918035454161`) |
| `ASSOCIATE_NUMBER` | Live associate number, E.164 (`+912264236412`) |
| `TARGET_NUMBER` | Optional default number to call (can also be typed in the UI) |
| `PUBLIC_URL` | Public HTTPS URL of the tunnel (no trailing slash) |
| `OTP` | Hardcoded birthdate in DDMM (`1110`) |

## Run & test

1. Start the server (listens on port 5050):
   ```bash
   .venv/bin/python app.py
   ```
2. Expose it publicly in another terminal and copy the `https://…` URL into `PUBLIC_URL` in `.env`, then restart the server:
   ```bash
   cloudflared tunnel --url http://localhost:5050     # or: ngrok http 5050
   ```
3. Open http://localhost:5050, enter your phone number (E.164, e.g. `+91…`) and click **Call me**.
   Or from the CLI:
   ```bash
   curl -X POST localhost:5050/call -H 'Content-Type: application/json' -d '{"to":"+91XXXXXXXXXX"}'
   ```
4. Answer the call and try:
   - OTP: enter a wrong code first (e.g. `0000`) → re-prompted; then `1110`.
   - Language: `1` English or `2` Spanish (any other key repeats the prompt).
   - Action: `1` plays the audio message, `2` forwards to the associate number.

## Files

- `app.py` — Flask app: `/call` (Plivo outbound API) and the XML endpoints `/answer`, `/otp`, `/language`, `/language/choice`, `/menu`, `/menu/choice`, `/dial-done`
- `templates/index.html` — one-page UI to trigger the call

## Notes

- Audio is Plivo's public sample MP3 (`AUDIO_URL` to override); prompts use Plivo `<Speak>` with `en-US` / `es-ES` voices.
- Never commit `.env`; it is gitignored. Rotate the Auth Token after the assessment.
