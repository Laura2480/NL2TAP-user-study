"""
Test E2E con sequenze di intent predefiniti per scenari expert e non-expert.

Simula utenti reali: per ogni scenario inviano intent predefiniti,
attendono la risposta dell'orchestrator, compilano la valutazione, e passano
allo scenario successivo. Gestisce anche i questionari interstitiali
(TOAST+TLX, SUS) tra i blocchi.

Tipo utente determinato automaticamente:
  non-expert: (id - 1) % 40 < 20  (user_1..20, 41..60, ...)
  expert:     (id - 1) % 40 >= 20 (user_21..40, 61..80, ...)

Prerequisiti:
  1. L'app Streamlit deve essere in esecuzione:
       streamlit run src/evaluation/Home.py
  2. Playwright installato:
       pip install playwright && playwright install chromium

Uso:
  python tests/test_e2e_scenarios.py                    # 1 utente, 6 scenari
  python tests/test_e2e_scenarios.py --users 3           # 3 in parallelo
  python tests/test_e2e_scenarios.py --users 9           # 9 in griglia 3x3
  python tests/test_e2e_scenarios.py --max-intents 1     # solo primo intent
  python tests/test_e2e_scenarios.py --skip-eval         # senza compilare valutazione
  python tests/test_e2e_scenarios.py --headless          # senza GUI
  python tests/test_e2e_scenarios.py --start 3001        # range utenti test
"""

import argparse
import asyncio
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import List, Optional

from playwright.async_api import async_playwright, Browser, Page

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "results", "study.db"
)

# ---------------------------------------------------------------------------
# Shared helpers (same as test_concurrent_users.py)
# ---------------------------------------------------------------------------

DEFAULT_URL = "http://localhost:8501"
ACCESS_CODE = "STUDY2026"
SCREEN_W, SCREEN_H = 1920, 1080
MAX_ATTEMPTS = 3


def _grid_layout(total: int, screen_w: int = SCREEN_W, screen_h: int = SCREEN_H):
    cols = math.ceil(math.sqrt(total))
    rows = math.ceil(total / cols)
    return cols, rows, screen_w // cols, screen_h // rows


def _grid_rect(index: int, total: int, screen_w: int = SCREEN_W, screen_h: int = SCREEN_H):
    cols, rows, cell_w, cell_h = _grid_layout(total, screen_w, screen_h)
    col = index % cols
    row = index // cols
    return col * cell_w, row * cell_h, cell_w, cell_h


def _print(text: str = ""):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


async def _position_window(page: Page, x: int, y: int, w: int, h: int):
    cdp = await page.context.new_cdp_session(page)
    resp = await cdp.send("Browser.getWindowForTarget")
    await cdp.send("Browser.setWindowBounds", {
        "windowId": resp["windowId"],
        "bounds": {"left": x, "top": y,
                   "width": max(w, 400), "height": max(h, 300),
                   "windowState": "normal"},
    })
    await cdp.detach()


async def _wait_for_streamlit(page: Page, timeout: float = 20_000):
    await page.wait_for_selector(
        '[data-testid="stAppViewContainer"]',
        state="visible", timeout=timeout,
    )
    await page.wait_for_timeout(800)


async def _wait_for_rerun(page: Page, ms: int = 2000):
    await page.wait_for_timeout(ms)


async def _is_on_home(page: Page) -> bool:
    """Detect if the page is showing Home (not Studio).

    Home has the login form or the study-complete summary, but NOT the
    scenario nav bar (``.sc-nav``).  We check for the absence of Studio
    indicators and presence of Home-specific elements.
    """
    # If the scenario nav bar is visible, we're on Studio
    try:
        await page.locator(".sc-nav").first.wait_for(state="visible", timeout=1_500)
        return False
    except Exception:
        pass
    # Check for Home-specific elements (login inputs, start button, or summary)
    home_indicators = page.locator(
        'input[aria-label="Nome utente"], '
        'input[aria-label="Username"], '
        'button:has-text("Inizia lo studio"), '
        'button:has-text("Start the study")'
    )
    try:
        await home_indicators.first.wait_for(state="visible", timeout=2_000)
        return True
    except Exception:
        # Could be a transition or loading state — not conclusively Home
        return False


async def _dismiss_tutorial(page: Page):
    """Dismiss the tutorial overlay if present.

    The tutorial injects ``#tutorial-spotlight`` + ``#tutorial-callout``
    into the parent document at z-index 50000+.  The skip button is
    ``#tc-skip`` inside the callout.  Clicking it fires a Streamlit
    component message that sets ``tutorial_active = False``.
    Uses JS click as fallback to avoid Playwright actionability timeouts
    under high concurrency.
    """
    skip_btn = page.locator("#tc-skip")
    try:
        await skip_btn.wait_for(state="visible", timeout=6_000)
    except Exception:
        return  # No tutorial showing
    _print("      [tutorial] dismissing...")
    try:
        await skip_btn.click(timeout=5_000)
    except Exception:
        # Fallback: JS click bypasses actionability checks
        await page.evaluate('document.getElementById("tc-skip")?.click()')
    await _wait_for_rerun(page, 2500)
    # Remove overlay via JS if it persists (server under load)
    await page.evaluate("""() => {
        document.getElementById('tutorial-spotlight')?.remove();
        document.getElementById('tutorial-callout')?.remove();
    }""")
    _print("      [tutorial] dismissed")


# ---------------------------------------------------------------------------
# Scenario intent sequences (Italian)
# ---------------------------------------------------------------------------

# User type is determined by: (id_num - 1) % 40 < 20 → non_expert, else expert
# Non-expert users: 1-20, 41-60, 81-100, ...
# Expert users:     21-40, 61-80, 101-120, ...

def _is_non_expert(user_num: int) -> bool:
    return (user_num - 1) % 40 < 20


NON_EXPERT_INTENTS = {
    # --- BLOCK 1 ---
    "S1": {  # Protezione piante dal freddo (C1)
        # Trigger: weather.tomorrows_weather_at_time -> Temperatura minima Celsius
        # Action: if_notifications.send_notification -> Messaggio
        "intents": [
            "Avvisami se domani fara molto freddo, devo mettere le piante al riparo",
            "Intendo quando la temperatura minima scende sotto i 2 gradi, mandami una notifica",
        ],
        "fallback": (
            "Quando il bollettino meteo di domani indica che la temperatura minima "
            "in Celsius sara sotto i 2 gradi, mandami una notifica con il messaggio "
            "che contiene la temperatura minima prevista"
        ),
        "eval": "matches_completely",
        "confidence": 4,
    },
    "M1": {  # Smart lock -> Spotify (C2)
        # Trigger: augusthome.lock_unlocked_by_specific_person -> Sbloccato a
        # Action: spotify.start_playback
        "intents": [
            "Quando sblocco la porta fai partire la musica su Spotify",
            "Solo di sera, dopo le 18, non voglio musica la mattina",
        ],
        "fallback": (
            "Quando la serratura smart viene sbloccata da una persona specifica "
            "e l'orario di sblocco e dopo le 18, avvia la riproduzione su Spotify"
        ),
        "eval": "matches_completely",
        "confidence": 4,
    },
    "C1": {  # CO2 -> LIFX lamp (C3)
        # Trigger: green_light_signal.co2_level -> Indice di Co2, Valore del livello di Co2
        # Action: lifx.color -> Colore
        "intents": [
            "Cambia il colore della lampada in base al livello di CO2",
            "Verde se il livello e basso, giallo se medio, rosso se alto",
        ],
        "fallback": (
            "Quando il livello di CO2 della rete cambia, imposta il colore "
            "della lampada LIFX: verde se il valore e basso, giallo se medio, "
            "rosso se alto. Usa l'indice di CO2 per decidere il colore"
        ),
        "eval": "partially",
        "confidence": 3,
    },
    # --- BLOCK 2 ---
    "S2": {  # Email -> Calendar (C1)
        # Trigger: email.send_ifttt_an_email -> Oggetto, Da, Corpo
        # Action: google_calendar.quick_add_event -> Testo evento rapido
        "intents": [
            "Quando ricevo un'email su una riunione aggiungila al calendario",
            "Solo se l'oggetto dell'email contiene la parola riunione o meeting",
        ],
        "fallback": (
            "Quando ricevo un'email su IFTTT e l'oggetto contiene la parola "
            "riunione o meeting, aggiungi un evento rapido su Google Calendar "
            "con il testo dell'oggetto dell'email"
        ),
        "eval": "matches_completely",
        "confidence": 4,
    },
    "M2": {  # Bus advisory -> SMS (C2)
        # Trigger: nj_transit.new_bus_advisory -> Itinerario e orario, Contenuto dell'avviso
        # Action: sms.send_me_text -> Messaggio
        "intents": [
            "Mandami un SMS quando c'e un avviso per il mio autobus",
            "Solo negli orari del tragitto, tra le 7 e le 9 di mattina, e solo per la linea 123",
        ],
        "fallback": (
            "Quando c'e un nuovo avviso per gli autobus NJ Transit e "
            "l'itinerario contiene la linea 123, mandami un SMS con il "
            "contenuto dell'avviso. Solo tra le 7 e le 9 di mattina"
        ),
        "eval": "matches_completely",
        "confidence": 3,
    },
    "C2": {  # RSS -> Dropbox (C3)
        # Trigger: feed.new_feed_item -> Titolo, URL, Contenuto, URL immagine
        # Action: dropbox.create_text_file_db + dropbox.add_file_from_url
        "intents": [
            "Salva gli articoli del mio feed RSS su Dropbox",
            "Crea un file di testo col contenuto e scarica anche l'immagine se presente",
        ],
        "fallback": (
            "Quando c'e un nuovo elemento nel feed RSS, crea un file di testo "
            "su Dropbox con il titolo e il contenuto della voce. Se c'e un URL "
            "immagine, aggiungi anche il file dall'URL immagine su Dropbox"
        ),
        "eval": "partially",
        "confidence": 3,
    },
}

EXPERT_INTENTS = {
    # --- BLOCK 1 ---
    "E2": {  # Tweet senza immagini -> Telegram (C1)
        # Trigger: twitter.new_tweet_by_user -> Testo, Collegamento al tweet
        # Action: telegram.send_message -> Testo del messaggio
        "intents": [
            "Quando un utente specifico pubblica un tweet, invialo su Telegram",
            "Solo se il tweet non contiene immagini, manda il testo e il link",
        ],
        "fallback": (
            "Quando c'e un nuovo tweet di un utente specifico e il testo non contiene "
            "link a immagini, invia un messaggio Telegram con il testo del tweet e il "
            "collegamento al tweet"
        ),
        "eval": "matches_completely",
        "confidence": 4,
    },
    "E1": {  # CO2 -> LIFX avanzato (C2)
        # Trigger: green_light_signal.co2_level -> Indice di Co2, Valore del livello
        # Action: lifx.color -> Colore, Luminosita
        "intents": [
            "Cambia il colore e la luminosita della lampada LIFX in base alla CO2",
            "Usa l'indice di CO2: verde e luminoso se basso, giallo medio, rosso fioco se alto",
        ],
        "fallback": (
            "Quando il livello di CO2 cambia, imposta il colore della lampada LIFX "
            "usando l'indice di CO2: verde con luminosita alta se basso, giallo con "
            "luminosita media se medio, rosso con luminosita bassa se alto"
        ),
        "eval": "partially",
        "confidence": 3,
    },
    "E3": {  # RSS -> Dropbox con condizioni (C3)
        # Trigger: feed.new_feed_item -> Titolo, Contenuto, URL immagine
        # Action: dropbox.create_text_file_db + dropbox.add_file_from_url
        "intents": [
            "Salva i nuovi articoli del feed RSS su Dropbox come file di testo",
            "Includi titolo e contenuto nel file, e se c'e un'immagine scaricala separatamente",
        ],
        "fallback": (
            "Quando c'e un nuovo elemento nel feed RSS, crea un file di testo su Dropbox "
            "con il titolo della voce e il contenuto. Se l'URL immagine della voce e presente, "
            "aggiungi anche il file dall'URL immagine su Dropbox"
        ),
        "eval": "partially",
        "confidence": 3,
    },
    # --- BLOCK 2 ---
    "E5": {  # NJ Transit -> SMS (C1)
        # Trigger: nj_transit.new_bus_advisory -> Itinerario e orario, Contenuto
        # Action: sms.send_me_text -> Messaggio
        "intents": [
            "Mandami un SMS quando c'e un avviso per gli autobus",
            "Solo per la mia linea, includi il contenuto dell'avviso nel messaggio",
        ],
        "fallback": (
            "Quando c'e un nuovo avviso per gli autobus NJ Transit e l'itinerario "
            "contiene la mia linea, mandami un SMS con il contenuto dell'avviso"
        ),
        "eval": "matches_completely",
        "confidence": 4,
    },
    "E4": {  # Instagram -> Facebook album (C2)
        # Trigger: instagram.any_new_photo_by_you -> Didascalia, URL
        # Action: facebook_pages.create_photo_page -> URL della foto, Messaggio, Nome album
        "intents": [
            "Pubblica le mie foto Instagram sulla pagina Facebook",
            "Organizza per mese: usa il mese corrente come nome dell'album",
        ],
        "fallback": (
            "Quando pubblico una nuova foto su Instagram, carica la foto dalla URL "
            "sulla pagina Facebook con la didascalia come messaggio e il mese di "
            "creazione come nome dell'album"
        ),
        "eval": "matches_completely",
        "confidence": 3,
    },
    "E6": {  # Twitter -> notifica + Feedly con orari silenziosi (C3)
        # Trigger: twitter.new_tweet_by_user -> Testo, Collegamento
        # Action: if_notifications.send_notification + feedly.create_new_entry_feedly
        "intents": [
            "Quando un utente twitta, avvisami e salva il tweet su Feedly",
            "Pero non mandarmi notifiche di notte, tra le 23 e le 7 salva solo su Feedly",
        ],
        "fallback": (
            "Quando c'e un nuovo tweet di un utente specifico, salva il collegamento "
            "al tweet su Feedly. Inoltre, se l'orario di creazione e tra le 7 e le 23, "
            "invia anche una notifica IFTTT con il testo del tweet"
        ),
        "eval": "partially",
        "confidence": 3,
    },
}

# Scenario order per user type (block1 then block2)
_NON_EXPERT_ORDER = ["S1", "M1", "C1", "S2", "M2", "C2"]
_EXPERT_ORDER = ["E2", "E1", "E3", "E5", "E4", "E6"]

# Map eval choices to Italian radio labels (non-expert has 4 options, expert has 3)
_EVAL_LABEL = {
    "matches_completely": "Corrisponde completamente",
    "partially": "Corrisponde parzialmente",
    "does_not_match": "Non corrisponde",
    "unsure": "Non sono sicuro/a",
}
_EVAL_LABEL_EN = {
    "matches_completely": "Matches completely",
    "partially": "Matches partially",
    "does_not_match": "Does not match",
    "unsure": "I'm not sure",
}

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    code: str
    ok: bool = False
    elapsed: float = 0.0
    error: str = ""
    intents_sent: int = 0
    eval_saved: bool = False
    fallback_used: bool = False
    latencies: List[float] = field(default_factory=list)  # server response times


@dataclass
class UserResult:
    user_id: str
    ok: bool = False
    elapsed: float = 0.0
    error: str = ""
    phase: str = "init"
    scenarios: List[ScenarioResult] = field(default_factory=list)
    questionnaires_ok: int = 0


# ---------------------------------------------------------------------------
# Core interaction helpers
# ---------------------------------------------------------------------------


async def _detect_l1_api_warnings(page: Page) -> bool:
    """Check if L1 validation produced API warnings (invalid getters/setters).

    The API warning block is rendered with a distinctive yellow border
    (``border:1px solid #f9a825``) and a ⚠️ icon.  This is the authoritative
    signal — it comes directly from L1 validation, not from the orchestrator
    text which may contain false positives.
    """
    try:
        found = await page.evaluate("""() => {
            // The API warning block has border color #f9a825
            const divs = document.querySelectorAll('div[style*="f9a825"]');
            return divs.length > 0;
        }""")
        return bool(found)
    except Exception:
        return False


async def _click_suggested_fields(page: Page) -> bool:
    """Click 'Select all fields' button if the orchestrator suggested fields.

    In condition B, suggested fields appear as clickable buttons with keys
    ``use_fields_{msg_index}`` (select all) or ``sug_f_{msg_index}_{fk}``
    (individual).  We prefer "select all" when available.
    Returns True if any field button was clicked.
    """
    await _js_scroll_bottom(page)

    # Try "select all" first
    select_all = page.locator('[class*="st-key-use_fields_"] button')
    try:
        await select_all.first.wait_for(state="visible", timeout=3_000)
        await select_all.first.click()
        _print("      [fields] clicked 'select all fields'")
        await _wait_for_rerun(page, 2000)
        return True
    except Exception:
        pass

    # Try individual field buttons (sug_f_)
    field_btns = page.locator('[class*="st-key-sug_f_"] button')
    try:
        count = await field_btns.count()
        if count > 0:
            clicked = 0
            for i in range(count):
                btn = field_btns.nth(i)
                try:
                    await btn.wait_for(state="visible", timeout=2_000)
                    await btn.click()
                    clicked += 1
                    await _wait_for_rerun(page, 1500)
                except Exception:
                    break
            _print(f"      [fields] clicked {clicked} individual field(s)")
            return clicked > 0
    except Exception:
        pass

    return False


async def _click_suggested_intent(page: Page) -> bool:
    """Click 'Use this intent' button if the orchestrator suggested a rewrite.

    In condition B, the orchestrator may suggest a rewritten intent with a
    diff view and a button with key ``use_suggestion_{msg_index}``.
    Clicking it prefills the chat input with the suggested text and triggers
    a Streamlit rerun.  Returns True if the button was clicked.
    """
    use_btn = page.locator('[class*="st-key-use_suggestion_"] button')
    try:
        await use_btn.first.wait_for(state="visible", timeout=3_000)
        await use_btn.first.click()
        _print("      [suggestion] clicked 'use this intent'")
        await _wait_for_rerun(page, 2000)
        return True
    except Exception:
        return False


async def send_intent(page: Page, text: str):
    """Write intent into the chat textarea and click submit.

    The chat form uses ``st.form()`` with a ``text_area`` +
    ``form_submit_button("➤")``.  The form only exists when the user
    still has attempts left (``_input_disabled`` is False).  If the form
    is absent (e.g. max attempts reached from a prior run), raise so the
    caller can handle it.

    Streamlit wraps the form in ``[data-testid="stForm"]`` and the submit
    button in ``[data-testid="stFormSubmitButton"]``.  The textarea inside
    the form has a dynamic key like ``chat_input_text_{N}``.
    """
    # Step 1 — Wait for the chat form itself
    form = page.locator('[data-testid="stForm"]')
    try:
        await form.first.wait_for(state="visible", timeout=10_000)
    except Exception:
        raise RuntimeError(
            "Chat form not found — the scenario may already have max attempts "
            "or the user is a returning user. Try a fresh user ID range."
        )

    # Step 2 — Fill the textarea inside the form
    textarea = form.locator("textarea").first
    await textarea.wait_for(state="visible", timeout=3_000)
    await textarea.click()
    await textarea.fill(text)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(200)

    # Step 3 — Click the form submit button
    submit_btn = form.locator(
        '[data-testid="stFormSubmitButton"] button, '
        'button[kind="formSubmit"], '
        'button'
    ).first
    await submit_btn.wait_for(state="visible", timeout=5_000)
    await submit_btn.click()


async def wait_for_response(page: Page, timeout: int = 90_000):
    """Wait for the orchestrator response to appear.

    After form submit, Streamlit reruns.  The orchestrator call shows a spinner
    while generating.  We wait for the spinner to appear then disappear.
    If the spinner never appears (very fast response or missed), we fall back
    to waiting for a new chat message or the eval section to show up.
    """
    await page.wait_for_timeout(500)

    spinner = page.locator('[data-testid="stSpinner"], .stSpinner')

    # Wait for spinner to appear (orchestrator started)
    spinner_appeared = False
    try:
        await spinner.first.wait_for(state="visible", timeout=4_000)
        spinner_appeared = True
    except Exception:
        pass

    if spinner_appeared:
        try:
            await spinner.first.wait_for(state="hidden", timeout=timeout)
        except Exception:
            pass
    else:
        try:
            await page.locator(
                '[class*="st-key-eval_section"]'
            ).first.wait_for(state="visible", timeout=timeout)
        except Exception:
            await page.wait_for_timeout(2000)

    # Settle time for Streamlit rerun
    await page.wait_for_timeout(800)


async def _js_scroll_bottom(page: Page):
    """Scroll to page bottom via JS (reliable, no timeout issues)."""
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(300)


async def fill_evaluation(page: Page, eval_choice: str, confidence: int,
                          is_expert: bool = False):
    """Select eval radio + confidence radio.

    **Non-expert** eval form:
      - ``eval_match_{SC}__{attempt}`` radio (4 options, incl. "unsure")
      - ``eval_conf_{SC}__{attempt}`` radio (1-5)

    **Expert** eval form:
      - ``eval_match_{SC}__{attempt}`` radio (3 options, no "unsure")
      - ``eval_code_correct_{SC}__{attempt}`` radio (yes/no)
      - ``eval_conf_expert_{SC}__{attempt}`` radio (1-5)

    Streamlit wraps each widget in a div with class ``st-key-{key}``.
    """
    label_text = _EVAL_LABEL.get(eval_choice, "Corrisponde completamente")

    # Scroll to bottom first — eval section is always at the end
    await _js_scroll_bottom(page)

    # --- Behavioral match radio (both user types) ---
    eval_container = page.locator('[class*="st-key-eval_match"]')
    try:
        await eval_container.first.wait_for(state="visible", timeout=10_000)
        label = eval_container.locator(f'label:has-text("{label_text}")')
        await label.first.click(timeout=8_000)
    except Exception:
        # English fallback
        en_text = _EVAL_LABEL_EN.get(eval_choice, "Matches completely")
        await page.locator(f'label:has-text("{en_text}")').first.click(timeout=5_000)
    await page.wait_for_timeout(300)

    if is_expert:
        # --- Code correctness radio (expert only) ---
        await _js_scroll_bottom(page)
        code_container = page.locator('[class*="st-key-eval_code_correct"]')
        try:
            await code_container.first.wait_for(state="visible", timeout=8_000)
            # Default to "yes" — test assumes generated code is acceptable
            yes_label = code_container.locator('label:has-text("yes"), label:has-text("si")')
            await yes_label.first.click(timeout=5_000)
        except Exception:
            _print("      [eval] code_correct radio not found, skipping")
        await page.wait_for_timeout(300)

        # --- Confidence radio (expert: key = eval_conf_expert_) ---
        conf_str = str(confidence)
        await _js_scroll_bottom(page)
        conf_container = page.locator('[class*="st-key-eval_conf_expert"]')
        try:
            await conf_container.first.wait_for(state="visible", timeout=8_000)
            label = conf_container.locator(f'label:has-text("{conf_str}")')
            await label.first.click(timeout=8_000)
        except Exception:
            # Fallback: pick last radio group on page
            radio_groups = page.locator('[data-testid="stRadio"]')
            count = await radio_groups.count()
            if count >= 2:
                conf_group = radio_groups.nth(count - 1)
                await conf_group.locator(
                    f'label:has-text("{conf_str}")'
                ).first.click(timeout=5_000)
        await page.wait_for_timeout(200)
    else:
        # --- Confidence radio (non-expert: key = eval_conf_) ---
        conf_str = str(confidence)
        await _js_scroll_bottom(page)
        conf_container = page.locator('[class*="st-key-eval_conf"]')
        try:
            await conf_container.first.wait_for(state="visible", timeout=8_000)
            label = conf_container.locator(f'label:has-text("{conf_str}")')
            await label.first.click(timeout=8_000)
        except Exception:
            radio_groups = page.locator('[data-testid="stRadio"]')
            count = await radio_groups.count()
            if count >= 2:
                conf_group = radio_groups.nth(count - 1)
                await conf_group.locator(
                    f'label:has-text("{conf_str}")'
                ).first.click(timeout=5_000)
        await page.wait_for_timeout(200)


async def click_save_eval(page: Page):
    """Click 'Salva valutazione' / 'Save evaluation' and wait for rerun."""
    await _js_scroll_bottom(page)
    save_btn = page.locator(
        'button:has-text("Salva valutazione"), '
        'button:has-text("Save evaluation")'
    )
    await save_btn.first.wait_for(state="visible", timeout=8_000)
    try:
        await save_btn.first.click(timeout=3_000)
    except Exception:
        await save_btn.first.click(force=True, timeout=3_000)
    await _wait_for_rerun(page, 2000)


async def _is_toast_tlx_showing(page: Page) -> bool:
    """Check if the TOAST+TLX interstitial is currently displayed.

    The TOAST section renders radio buttons with keys ``toast_q{N}_block{B}``
    which Streamlit wraps in ``[class*="st-key-toast_q"]`` containers.
    The TLX section has sliders with keys ``tlx_{name}_block{B}``.
    We check for the TOAST radio presence as the primary signal.
    """
    indicator = page.locator('[class*="st-key-toast_q"]')
    try:
        await indicator.first.wait_for(state="visible", timeout=4_000)
        return True
    except Exception:
        return False


async def handle_questionnaire(page: Page) -> bool:
    """Handle the unified TOAST+TLX+SUS questionnaire page.

    All three sections (TOAST radio, TLX sliders, SUS sliders) are now
    rendered on a single scrollable page with one submit button at the
    bottom (key ``questionnaire_submit_{block}``).
    We detect it via the TOAST radio widgets, scroll to the submit, click.
    """
    if not await _is_toast_tlx_showing(page):
        return False

    _print("      [questionnaire] detected — scrolling to submit...")
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(500)

    submit_btn = page.locator(
        '[class*="st-key-questionnaire_submit"] button'
    )
    try:
        await submit_btn.first.wait_for(state="visible", timeout=5_000)
    except Exception:
        submit_btn = page.locator(
            'button:has-text("Invia e continua"), '
            'button:has-text("Submit and continue"), '
            'button:has-text("Invia questionario finale"), '
            'button:has-text("Submit final questionnaire")'
        )
        await submit_btn.first.wait_for(state="visible", timeout=3_000)

    await submit_btn.first.scroll_into_view_if_needed()
    await submit_btn.first.click()
    await _wait_for_rerun(page, 2500)
    _print("      [questionnaire] TOAST+TLX+SUS submitted")
    return True


async def handle_interstitials(page: Page) -> int:
    """Handle any interstitial questionnaires that appear.

    After a block is completed, TOAST+TLX+SUS appear on one page.
    Returns 1 if the questionnaire was handled, 0 otherwise.
    """
    if await handle_questionnaire(page):
        await _wait_for_rerun(page, 1500)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Scenario flow
# ---------------------------------------------------------------------------


async def do_scenario(
    page: Page,
    scenario_code: str,
    max_intents: int = 0,
    skip_eval: bool = False,
    is_expert: bool = False,
) -> ScenarioResult:
    """Run a complete scenario: send intents -> eval -> save."""
    intent_dict = EXPERT_INTENTS if is_expert else NON_EXPERT_INTENTS
    spec = intent_dict.get(scenario_code)
    if not spec:
        return ScenarioResult(code=scenario_code, error="no intent spec")

    result = ScenarioResult(code=scenario_code)
    t0 = time.monotonic()

    try:
        intents = list(spec["intents"])
        if max_intents > 0:
            intents = intents[:max_intents]

        # Send each intent in sequence
        for i, intent_text in enumerate(intents):
            _print(f"      intent {i+1}/{len(intents)}: sending...")
            await send_intent(page, intent_text)
            result.intents_sent += 1

            _print(f"      intent {i+1}/{len(intents)}: waiting for response...")
            _t_req = time.monotonic()
            await wait_for_response(page, timeout=90_000)
            _latency = time.monotonic() - _t_req
            result.latencies.append(_latency)
            _print(f"      intent {i+1}/{len(intents)}: response received ({_latency:.1f}s)")

            # After each response, interact with suggestions if present
            # 1. Click suggested fields (condition B)
            await _click_suggested_fields(page)

            # 2. Check for suggested intent (condition B) — but DON'T click
            #    it yet; we send our own next intent first.
            #    (We'll use it after all intents are sent, if L1 still warns.)

        # After all intents sent, check L1 validation for API warnings.
        # L1 is the authoritative source — the yellow ⚠️ block appears when
        # there are invalid getters/setters in the generated code.
        has_l1_warnings = await _detect_l1_api_warnings(page)

        if has_l1_warnings and not skip_eval:
            # First try: click suggested intent if orchestrator offered one
            # (condition B).  This prefills the chat input.
            used_suggestion = await _click_suggested_intent(page)
            if used_suggestion:
                # The suggestion was prefilled — now submit the form
                form = page.locator('[data-testid="stForm"]')
                try:
                    await form.first.wait_for(state="visible", timeout=5_000)
                    submit_btn = form.locator(
                        '[data-testid="stFormSubmitButton"] button, '
                        'button[kind="formSubmit"], button'
                    ).first
                    await submit_btn.click()
                    result.intents_sent += 1
                    _print("      [suggestion] submitted prefilled intent")
                    await wait_for_response(page, timeout=120_000)
                    _print("      [suggestion] response received")
                    # Click any newly suggested fields
                    await _click_suggested_fields(page)
                except Exception:
                    _print("      [suggestion] could not submit prefilled form")
            else:
                # No suggestion available (condition A or none offered) —
                # fall back to our predefined corrected intent
                fallback = spec.get("fallback")
                if fallback:
                    _print("      [fallback] L1 API warnings, sending corrected intent...")
                    await send_intent(page, fallback)
                    result.intents_sent += 1
                    result.fallback_used = True
                    await wait_for_response(page, timeout=120_000)
                    _print("      [fallback] response received")
                    await _click_suggested_fields(page)

        # Fill evaluation form
        if not skip_eval:
            _print(f"      filling evaluation...")

            await fill_evaluation(page, spec["eval"], spec["confidence"],
                                  is_expert=is_expert)
            await click_save_eval(page)
            result.eval_saved = True
            _print(f"      evaluation saved")

        result.ok = True

    except Exception as e:
        err_msg = str(e).split("\n")[0][:150]
        result.error = f"{type(e).__name__}: {err_msg}"

    result.elapsed = time.monotonic() - t0
    return result


# ---------------------------------------------------------------------------
# Single user E2E flow
# ---------------------------------------------------------------------------


async def run_single_user(
    browser: Browser,
    index: int,
    user_num: int,
    base_url: str,
    total_users: int,
    max_intents: int = 0,
    skip_eval: bool = False,
    stagger_ms: int = 0,
    headless: bool = False,
) -> UserResult:
    """Full E2E flow: Login -> Start -> [scenarios + interstitials] -> End."""
    user_id = f"user_{user_num}"
    _clean_user_db(user_id)
    _print(f"  [{user_id}] DB cleaned")
    result = UserResult(user_id=user_id)
    t0 = time.monotonic()

    try:
        if stagger_ms > 0:
            await asyncio.sleep(stagger_ms / 1000.0)

        x, y, w, h = _grid_rect(index, total_users)

        context = await browser.new_context(
            viewport={"width": max(w - 16, 400), "height": max(h - 80, 300)},
        )
        page = await context.new_page()

        if not headless:
            try:
                await _position_window(page, x, y, w, h)
            except Exception:
                pass

        # -- Phase 1: Navigate --
        result.phase = "navigate"
        _print(f"  [{user_id}] navigating...")
        await page.goto(base_url, wait_until="domcontentloaded")

        # Bypass ngrok interstitial ("Visit Site" button) if present
        try:
            ngrok_btn = page.locator(
                'button:has-text("Visit Site"), '
                'a:has-text("Visit Site")'
            )
            await ngrok_btn.first.wait_for(state="visible", timeout=3_000)
            await ngrok_btn.first.click()
            _print(f"  [{user_id}] bypassed ngrok interstitial")
            await page.wait_for_timeout(2000)
        except Exception:
            pass  # Not ngrok or no interstitial

        await _wait_for_streamlit(page, timeout=45_000)

        # -- Phase 2: Login --
        result.phase = "login"
        _print(f"  [{user_id}] logging in...")

        username_input = page.locator(
            'input[aria-label="Nome utente"], input[aria-label="Username"]'
        )
        await username_input.first.wait_for(state="visible", timeout=10_000)
        await username_input.first.fill(user_id)

        password_input = page.locator(
            'input[aria-label="Codice di accesso"], input[aria-label="Access code"]'
        )
        await password_input.first.fill(ACCESS_CODE)

        login_btn = page.locator(
            'button:has-text("Accedi"), button:has-text("Log in")'
        )
        await login_btn.first.click()
        await _wait_for_rerun(page, 2500)

        # -- Phase 3: Start study --
        result.phase = "start_study"

        # Check if already on Studio
        studio_indicator = page.locator('.sc-nav, textarea, [data-testid="stForm"]')
        try:
            await studio_indicator.first.wait_for(state="visible", timeout=3_000)
            _print(f"  [{user_id}] already on Studio (returning user)")
        except Exception:
            start_btn = page.locator(
                'button:has-text("Inizia lo studio"), '
                'button:has-text("Start the study"), '
                'button:has-text("Riprendi lo studio"), '
                'button:has-text("Resume the study")'
            )
            await start_btn.first.wait_for(state="visible", timeout=10_000)
            await start_btn.first.click()
            _print(f"  [{user_id}] clicked Start...")
            await _wait_for_rerun(page, 3000)

        # -- Phase 4: Studio loaded --
        result.phase = "studio_loaded"
        await page.wait_for_selector(
            '.sc-nav, textarea, [data-testid="stForm"]',
            state="visible", timeout=12_000,
        )
        _print(f"  [{user_id}] Studio loaded")

        # -- Phase 4b: Dismiss tutorial (first-time users) --
        await _dismiss_tutorial(page)

        # -- Phase 5: Run through scenarios --
        result.phase = "scenarios"

        # Determine user type and scenario order
        is_expert = not _is_non_expert(user_num)
        user_type_tag = "expert" if is_expert else "non_expert"
        _print(f"  [{user_id}] user_type={user_type_tag}")

        intent_dict = EXPERT_INTENTS if is_expert else NON_EXPERT_INTENTS
        ordered_codes = _EXPERT_ORDER if is_expert else _NON_EXPERT_ORDER

        scenario_count = 0
        max_scenarios = len(intent_dict)
        _interstitial_retries = 0
        _MAX_INTERSTITIAL_RETRIES = 4  # at most 2 blocks × 2 questionnaires

        while scenario_count < max_scenarios:
            # Check if we landed on Home (study complete — SUS block 2 redirects here)
            if await _is_on_home(page):
                _print(f"  [{user_id}] redirected to Home -- study complete")
                break

            # Wait for the chat form (scenario page) to appear
            form_visible = False
            try:
                await page.locator('[data-testid="stForm"]').first.wait_for(
                    state="visible", timeout=8_000,
                )
                form_visible = True
                _interstitial_retries = 0
            except Exception:
                # Maybe an interstitial appeared (TOAST+TLX or SUS)
                if _interstitial_retries < _MAX_INTERSTITIAL_RETRIES:
                    q_handled = await handle_interstitials(page)
                    result.questionnaires_ok += q_handled
                    _interstitial_retries += 1
                    if q_handled > 0:
                        # After SUS, might redirect to Home
                        if await _is_on_home(page):
                            _print(f"  [{user_id}] redirected to Home -- study complete")
                            break
                        continue
                _print(f"  [{user_id}] no chat form found — breaking")
                break

            if not form_visible:
                break

            # Determine the current scenario code from the ordered list
            if scenario_count < len(ordered_codes):
                sc_code = ordered_codes[scenario_count]
            else:
                sc_code = f"UNK_{scenario_count}"

            _print(f"  [{user_id}] scenario {scenario_count+1}/{max_scenarios}: {sc_code}")

            sc_result = await do_scenario(
                page, sc_code,
                max_intents=max_intents,
                skip_eval=skip_eval,
                is_expert=is_expert,
            )
            result.scenarios.append(sc_result)
            scenario_count += 1

            status = "OK" if sc_result.ok else "FAIL"
            fb_tag = " FB" if sc_result.fallback_used else ""
            _print(
                f"  [{user_id}] {sc_code}[{status}{fb_tag} {sc_result.elapsed:.0f}s]"
                + (f" -- {sc_result.error}" if sc_result.error else "")
            )

            # After saving eval, the page auto-advances to next scenario.
            # But there might be a questionnaire (after block completion).
            # The save triggers: rerun → complete_scenario → detect block
            # done → set _show_toast → rerun again → render questionnaire.
            if sc_result.eval_saved:
                await page.wait_for_timeout(3000)  # wait for double-rerun
                q_handled = await handle_interstitials(page)
                result.questionnaires_ok += q_handled
                if q_handled > 0 and await _is_on_home(page):
                    _print(f"  [{user_id}] redirected to Home -- study complete")
                    break

        result.phase = "done"
        result.ok = all(s.ok for s in result.scenarios)

    except Exception as e:
        err_msg = str(e).split("\n")[0][:150]
        result.error = f"[{result.phase}] {type(e).__name__}: {err_msg}"

    result.elapsed = time.monotonic() - t0
    return result


# ---------------------------------------------------------------------------
# DB cleanup
# ---------------------------------------------------------------------------


def _clean_user_db(user_id: str):
    """Remove all DB rows for a test user so the run starts clean.

    Only works when running against a local Streamlit instance (DB is on
    the same machine).  Silently skips if the DB file is not found (e.g.
    when running against a remote ngrok URL).
    """
    if not os.path.exists(_DB_PATH):
        return
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    _tables = [
        "interactions", "scenario_sessions",
        "toast_responses", "sus_responses", "tlx_responses",
    ]
    for t in _tables:
        try:
            c.execute(f"DELETE FROM {t} WHERE participant_id = ?", (user_id,))
        except Exception:
            pass
    try:
        c.execute("DELETE FROM participants WHERE participant_id = ?", (user_id,))
    except Exception:
        pass
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def run_e2e_test(
    n_users: int = 1,
    base_url: str = DEFAULT_URL,
    headless: bool = False,
    max_intents: int = 0,
    skip_eval: bool = False,
    slow_mo: int = 0,
    stagger_ms: int = 1000,
    start_id: int = 3001,
):
    end_id = start_id + n_users - 1
    cols, rows, cw, ch = _grid_layout(n_users)

    # Show user type breakdown
    user_types = []
    for i in range(n_users):
        uid = start_id + i
        utype = "NE" if _is_non_expert(uid) else "EX"
        user_types.append(f"user_{uid}({utype})")

    _print(f"\n{'='*60}")
    _print(f"  TEST E2E -- {n_users} utenti")
    _print(f"  Range: user_{start_id} .. user_{end_id}")
    _print(f"  Types: {', '.join(user_types)}")
    _print(f"  Griglia: {cols}x{rows}  (celle {cw}x{ch} px)")
    _print(f"  URL: {base_url}")
    _print(f"  Headless: {headless}  |  Stagger: {stagger_ms}ms")
    _print(f"  Max intents: {max_intents or 'all'}  |  Skip eval: {skip_eval}")
    _print(f"{'='*60}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=["--disable-blink-features=AutomationControlled"],
        )

        t_start = time.monotonic()
        tasks = [
            run_single_user(
                browser=browser,
                index=i,
                user_num=start_id + i,
                base_url=base_url,
                total_users=n_users,
                max_intents=max_intents,
                skip_eval=skip_eval,
                stagger_ms=i * stagger_ms,
                headless=headless,
            )
            for i in range(n_users)
        ]
        results: List[UserResult] = await asyncio.gather(*tasks)
        t_total = time.monotonic() - t_start

        # -- Report --
        _print(f"\n{'='*60}")
        _print(f"  RISULTATI E2E")
        _print(f"{'='*60}\n")

        total_scenarios = 0
        ok_scenarios = 0
        fallback_count = 0
        all_times = []

        for r in results:
            parts = []
            for s in r.scenarios:
                tag = "OK" if s.ok else "FAIL"
                fb = " FB" if s.fallback_used else ""
                parts.append(f"{s.code}[{tag}{fb} {s.elapsed:.0f}s]")
                total_scenarios += 1
                if s.ok:
                    ok_scenarios += 1
                    all_times.append(s.elapsed)
                if s.fallback_used:
                    fallback_count += 1

            line = f"  {r.user_id:>12s}  "
            # Group by block (first 3 + separator + last 3)
            if len(parts) >= 6:
                line += " ".join(parts[:3])
                line += f" | Q[{r.questionnaires_ok}] | "
                line += " ".join(parts[3:])
            else:
                line += " ".join(parts)

            line += f"  TOTAL: {r.elapsed:.0f}s"
            if r.error:
                line += f"  -- {r.error}"
            _print(line)

        # Collect all latencies
        all_latencies = []
        for r in results:
            for s in r.scenarios:
                all_latencies.extend(s.latencies)

        _print(f"\n  {'-'*50}")
        _print(f"  Successi: {ok_scenarios}/{total_scenarios} scenari")
        if fallback_count:
            _print(f"  Fallback usati: {fallback_count}")
        if all_times:
            avg = sum(all_times) / len(all_times)
            _print(f"  Tempo medio/scenario: {avg:.1f}s")
        _print(f"  Tempo totale: {t_total:.1f}s")

        # Latency report
        if all_latencies:
            all_latencies.sort()
            n = len(all_latencies)
            _avg = sum(all_latencies) / n
            _p50 = all_latencies[n // 2]
            _p90 = all_latencies[int(n * 0.9)]
            _p99 = all_latencies[int(n * 0.99)]
            _mn = all_latencies[0]
            _mx = all_latencies[-1]
            _print(f"\n  {'='*50}")
            _print(f"  SERVER LATENCY ({n} requests, {n_users} concurrent)")
            _print(f"  {'='*50}")
            _print(f"  avg: {_avg:.1f}s  |  p50: {_p50:.1f}s  |  p90: {_p90:.1f}s  |  p99: {_p99:.1f}s")
            _print(f"  min: {_mn:.1f}s  |  max: {_mx:.1f}s")
        _print()

        # Keep windows open for inspection
        if not headless:
            _print("  Le finestre restano aperte. Premi INVIO per chiudere...")
            try:
                await asyncio.get_event_loop().run_in_executor(None, input)
            except EOFError:
                _print("  (stdin non interattivo, chiusura in 10s...)")
                await asyncio.sleep(10)

        await browser.close()

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Test E2E con sequenze di intent per scenari non-expert"
    )
    parser.add_argument(
        "--users", "-n", type=int, default=1,
        help="Numero di utenti simultanei (default: 1)",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8501,
        help="Porta Streamlit (default: 8501)",
    )
    parser.add_argument(
        "--url", type=str, default="",
        help="URL completo (es. https://abc123.ngrok-free.app). Sovrascrive --port",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Esegui senza finestre visibili",
    )
    parser.add_argument(
        "--max-intents", type=int, default=0,
        help="Limita il numero di intent per scenario (0 = tutti, default: 0)",
    )
    parser.add_argument(
        "--skip-eval", action="store_true",
        help="Non compilare il form di valutazione",
    )
    parser.add_argument(
        "--slow-mo", type=int, default=0,
        help="Rallenta ogni azione di N ms (per debug)",
    )
    parser.add_argument(
        "--stagger", type=int, default=1000,
        help="Ritardo tra avvio utenti in ms (default: 1000)",
    )
    parser.add_argument(
        "--start", type=int, default=3001,
        help="ID primo utente, es. 3001 -> user_3001.. (default: 3001)",
    )

    args = parser.parse_args()
    base_url = args.url.rstrip("/") if args.url else f"http://localhost:{args.port}"

    asyncio.run(
        run_e2e_test(
            n_users=args.users,
            base_url=base_url,
            headless=args.headless,
            max_intents=args.max_intents,
            skip_eval=args.skip_eval,
            slow_mo=args.slow_mo,
            stagger_ms=args.stagger,
            start_id=args.start,
        )
    )


if __name__ == "__main__":
    main()
