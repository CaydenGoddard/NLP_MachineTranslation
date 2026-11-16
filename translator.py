"""Translation service clients for NLP_MachineTranslation.

Every service is wrapped in a small class with the same interface:

    translate(text, source_lang, target_lang) -> str

Because they all look the same, main.py can loop over them and put the
outputs side by side without caring which API produced which result.

Supported services:
    DeepL                       (DEEPL_API_KEY)
    Google Cloud Translation    (GOOGLE_API_KEY)
    Microsoft Azure Translator  (AZURE_TRANSLATOR_KEY, AZURE_TRANSLATOR_REGION)
    MyMemory                    (no key needed; ENABLE_MYMEMORY=true)

A service is only used when its key is present in .env, so the program
runs with whichever services you have set up.
"""

import html
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

TIMEOUT_SECONDS = 20


class TranslationError(Exception):
    """Raised when a service fails to return a translation."""


def _request(method, url, **kwargs):
    """Send an HTTP request and return the parsed JSON, or raise TranslationError."""
    try:
        response = requests.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
    except requests.RequestException as exc:
        raise TranslationError(f"network error: {exc}") from exc

    if response.status_code != 200:
        raise TranslationError(f"HTTP {response.status_code}: {response.text[:200]}")

    try:
        return response.json()
    except ValueError as exc:
        raise TranslationError("response was not valid JSON") from exc


class Translator:
    """Base class: every service implements is_configured() and translate()."""

    name = "Base"

    def is_configured(self) -> bool:
        return True

    def missing_config_message(self) -> str:
        return ""

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        raise NotImplementedError


class DeepLTranslator(Translator):
    name = "DeepL"

    # DeepL requires a regional variant for some target languages.
    TARGET_VARIANTS = {"EN": "EN-US", "PT": "PT-BR"}

    def __init__(self, api_key=None):
        self.api_key = (api_key or os.getenv("DEEPL_API_KEY", "")).strip()

    def is_configured(self):
        return bool(self.api_key)

    def missing_config_message(self):
        return "set DEEPL_API_KEY in .env"

    @property
    def url(self):
        # Free-tier keys end in ":fx" and use a separate host.
        host = "api-free.deepl.com" if self.api_key.endswith(":fx") else "api.deepl.com"
        return f"https://{host}/v2/translate"

    def translate(self, text, source_lang, target_lang):
        target = target_lang.upper()
        target = self.TARGET_VARIANTS.get(target, target)
        data = _request(
            "POST",
            self.url,
            headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            json={
                "text": [text],
                "source_lang": source_lang.upper(),
                "target_lang": target,
            },
        )
        try:
            return data["translations"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise TranslationError(f"unexpected DeepL response: {data}") from exc


class GoogleTranslator(Translator):
    name = "Google"
    URL = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, api_key=None):
        self.api_key = (api_key or os.getenv("GOOGLE_API_KEY", "")).strip()

    def is_configured(self):
        return bool(self.api_key)

    def missing_config_message(self):
        return "set GOOGLE_API_KEY in .env"

    def translate(self, text, source_lang, target_lang):
        data = _request(
            "POST",
            self.URL,
            params={"key": self.api_key},
            json={
                "q": text,
                "source": source_lang.lower(),
                "target": target_lang.lower(),
                "format": "text",
            },
        )
        try:
            # Google can return HTML entities like &#39; - convert them back.
            return html.unescape(data["data"]["translations"][0]["translatedText"])
        except (KeyError, IndexError) as exc:
            raise TranslationError(f"unexpected Google response: {data}") from exc


class AzureTranslator(Translator):
    name = "Microsoft"
    URL = "https://api.cognitive.microsofttranslator.com/translate"

    def __init__(self, api_key=None, region=None):
        self.api_key = (api_key or os.getenv("AZURE_TRANSLATOR_KEY", "")).strip()
        self.region = (region or os.getenv("AZURE_TRANSLATOR_REGION", "")).strip()

    def is_configured(self):
        return bool(self.api_key)

    def missing_config_message(self):
        return "set AZURE_TRANSLATOR_KEY (and AZURE_TRANSLATOR_REGION) in .env"

    def translate(self, text, source_lang, target_lang):
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        data = _request(
            "POST",
            self.URL,
            params={"api-version": "3.0", "from": source_lang.lower(), "to": target_lang.lower()},
            headers=headers,
            json=[{"Text": text}],
        )
        try:
            return data[0]["translations"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError(f"unexpected Azure response: {data}") from exc


class MyMemoryTranslator(Translator):
    """Free translation-memory API that needs no key (limited daily quota)."""

    name = "MyMemory"
    URL = "https://api.mymemory.translated.net/get"

    def __init__(self):
        self.enabled = os.getenv("ENABLE_MYMEMORY", "true").strip().lower() in ("1", "true", "yes")
        self.email = os.getenv("MYMEMORY_EMAIL", "").strip()  # optional, raises the quota

    def is_configured(self):
        return self.enabled

    def missing_config_message(self):
        return "set ENABLE_MYMEMORY=true in .env"

    def translate(self, text, source_lang, target_lang):
        params = {"q": text, "langpair": f"{source_lang.lower()}|{target_lang.lower()}"}
        if self.email:
            params["de"] = self.email
        data = _request("GET", self.URL, params=params)
        if str(data.get("responseStatus")) != "200":
            raise TranslationError(f"MyMemory error: {data.get('responseDetails')}")
        return html.unescape(data["responseData"]["translatedText"])


ALL_TRANSLATORS = [DeepLTranslator, GoogleTranslator, AzureTranslator, MyMemoryTranslator]


def get_translators(verbose=True):
    """Return instances of every service that has its configuration set."""
    active = []
    for cls in ALL_TRANSLATORS:
        translator = cls()
        if translator.is_configured():
            active.append(translator)
        elif verbose:
            print(f"[skip] {translator.name}: {translator.missing_config_message()}")
    return active


def compare_translations(text, source_lang, target_lang, translators):
    """Send the same text to every service and collect the results.

    Returns a list of dicts: {service, translation, error, seconds}.
    A failing service does not stop the others; its error is recorded instead.
    """
    results = []
    for translator in translators:
        start = time.perf_counter()
        try:
            translation = translator.translate(text, source_lang, target_lang)
            error = ""
        except TranslationError as exc:
            translation = ""
            error = str(exc)
        results.append(
            {
                "service": translator.name,
                "translation": translation,
                "error": error,
                "seconds": round(time.perf_counter() - start, 2),
            }
        )
    return results
