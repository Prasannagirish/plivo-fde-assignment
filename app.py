"""InspireWorks demo IVR: outbound call -> OTP auth -> language menu -> action menu (Plivo XML)."""
import os
from urllib.parse import urlencode

import plivo
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from plivo import plivoxml

load_dotenv()

AUTH_ID = os.environ["PLIVO_AUTH_ID"]
AUTH_TOKEN = os.environ["PLIVO_AUTH_TOKEN"]
PLIVO_NUMBER = os.environ.get("PLIVO_NUMBER", "+918035454161")
ASSOCIATE_NUMBER = os.environ.get("ASSOCIATE_NUMBER", "+912264236412")
DEFAULT_TARGET = os.environ.get("TARGET_NUMBER", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
OTP = os.environ.get("OTP", "1110")  # birthdate, DDMM (11 October)
AUDIO_URL = os.environ.get("AUDIO_URL", "https://s3.amazonaws.com/plivocloud/Trumpet.mp3")

app = Flask(__name__)
client = plivo.RestClient(AUTH_ID, AUTH_TOKEN)

# Prompt text + TTS locale per language.
LANGS = {
    "en": {
        "tts": "en-US",
        "menu": "Press 1 to play a short audio message. Press 2 to speak with a live associate.",
        "invalid": "Sorry, that was not a valid option.",
        "audio_intro": "Playing your audio message.",
        "connecting": "Connecting you to a live associate. Please hold.",
        "bye": "Thank you for calling InspireWorks. Goodbye.",
        "no_answer": "We could not reach an associate. Goodbye.",
    },
    "es": {
        "tts": "es-ES",
        "menu": "Presione 1 para escuchar un mensaje de audio breve. Presione 2 para hablar con un asociado.",
        "invalid": "Lo sentimos, esa opción no es válida.",
        "audio_intro": "Reproduciendo su mensaje de audio.",
        "connecting": "Conectándolo con un asociado. Por favor espere.",
        "bye": "Gracias por llamar a InspireWorks. Adiós.",
        "no_answer": "No pudimos comunicarnos con un asociado. Adiós.",
    },
}


def base_url():
    return PUBLIC_URL or request.host_url.rstrip("/")


def url(path, **params):
    q = f"?{urlencode(params)}" if params else ""
    return f"{base_url()}{path}{q}"


def xml(resp):
    return Response(resp.to_string(), mimetype="text/xml")


def speak(parent, text, lang="en"):
    parent.add_speak(text, language=LANGS[lang]["tts"], voice="WOMAN")  # returns parent; nesting is by call target


def digits():
    return (request.values.get("Digits") or "").strip()


# ---------- Outbound call trigger ----------

@app.get("/")
def index():
    return render_template("index.html", default_target=DEFAULT_TARGET, from_number=PLIVO_NUMBER)


@app.post("/call")
def call():
    target = (request.json or {}).get("to", "").strip() or DEFAULT_TARGET
    if not target:
        return jsonify(error="No target number provided"), 400
    try:
        r = client.calls.create(
            from_=PLIVO_NUMBER,
            to_=target,
            answer_url=url("/answer"),
            answer_method="POST",
        )
    except Exception as e:  # surface Plivo errors (e.g. unverified trial number) in the UI
        return jsonify(error=str(e)), 502
    return jsonify(message=r.message, request_uuid=r.request_uuid)


# ---------- IVR: Level 0 - OTP ----------

@app.route("/answer", methods=["GET", "POST"])
def answer():
    """Prompt for the 4-digit OTP. Falls through to a redirect (re-prompt) on timeout."""
    resp = plivoxml.ResponseElement()
    gd = plivoxml.GetDigitsElement(action=url("/otp"), method="POST", num_digits=4, timeout=10)
    speak(gd, "Welcome to InspireWorks. Please enter your 4 digit one time password.")
    resp.add(gd)
    speak(resp, "We did not receive any input.")
    resp.add_redirect(url("/answer"), method="POST")
    return xml(resp)


@app.post("/otp")
def otp():
    resp = plivoxml.ResponseElement()
    if digits() == OTP:
        speak(resp, "Thank you. You have been authenticated.")
        resp.add_redirect(url("/language"), method="POST")
    else:
        speak(resp, "That password is incorrect. Please try again.")
        resp.add_redirect(url("/answer"), method="POST")
    return xml(resp)


# ---------- IVR: Level 1 - language ----------

@app.route("/language", methods=["GET", "POST"])
def language():
    resp = plivoxml.ResponseElement()
    gd = plivoxml.GetDigitsElement(action=url("/language/choice"), method="POST", num_digits=1, timeout=8)
    speak(gd, "For English, press 1.", "en")
    speak(gd, "Para español, presione 2.", "es")
    resp.add(gd)
    resp.add_redirect(url("/language"), method="POST")
    return xml(resp)


@app.post("/language/choice")
def language_choice():
    resp = plivoxml.ResponseElement()
    lang = {"1": "en", "2": "es"}.get(digits())
    if lang:
        resp.add_redirect(url("/menu", lang=lang), method="POST")
    else:
        speak(resp, "Sorry, that was not a valid option. Lo sentimos, esa opción no es válida.")
        resp.add_redirect(url("/language"), method="POST")
    return xml(resp)


# ---------- IVR: Level 2 - action ----------

@app.route("/menu", methods=["GET", "POST"])
def menu():
    lang = request.args.get("lang", "en")
    resp = plivoxml.ResponseElement()
    gd = plivoxml.GetDigitsElement(action=url("/menu/choice", lang=lang), method="POST", num_digits=1, timeout=8)
    speak(gd, LANGS[lang]["menu"], lang)
    resp.add(gd)
    resp.add_redirect(url("/menu", lang=lang), method="POST")
    return xml(resp)


@app.post("/menu/choice")
def menu_choice():
    lang = request.args.get("lang", "en")
    t = LANGS[lang]
    resp = plivoxml.ResponseElement()
    d = digits()
    if d == "1":
        speak(resp, t["audio_intro"], lang)
        resp.add_play(AUDIO_URL)
        speak(resp, t["bye"], lang)
        resp.add_hangup()
    elif d == "2":
        speak(resp, t["connecting"], lang)
        dial = plivoxml.DialElement(caller_id=PLIVO_NUMBER, timeout=30, action=url("/dial-done", lang=lang), method="POST")
        dial.add_number(ASSOCIATE_NUMBER)
        resp.add(dial)
    else:
        speak(resp, t["invalid"], lang)
        resp.add_redirect(url("/menu", lang=lang), method="POST")
    return xml(resp)


@app.post("/dial-done")
def dial_done():
    """Runs after the associate leg ends (or never connected)."""
    lang = request.args.get("lang", "en")
    resp = plivoxml.ResponseElement()
    speak(resp, LANGS[lang]["bye"], lang)
    resp.add_hangup()
    return xml(resp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5050)))
