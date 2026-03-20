#!/usr/bin/env python3
"""
Standalone E2E smoke-test — single file, zero local dependencies.

Simulates a real participant going through the full NL2TAP study:
  login → 6 scenarios (intents + eval) → 2 questionnaires → thank-you

Requirements (on any machine):
  pip install playwright && playwright install chromium

Usage:
  python remote_test.py --url https://xxxx.ngrok-free.app
  python remote_test.py --url https://xxxx.ngrok-free.app --user user_9001
  python remote_test.py --url https://xxxx.ngrok-free.app --headless
  python remote_test.py --url http://localhost:8501 --user user_4001
"""

import argparse
import asyncio
import time
from playwright.async_api import async_playwright, Page

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ACCESS_CODE = "STUDY2026"

# Predefined intents per scenario (Italian, 2 per scenario)
INTENTS = {
    # Non-expert scenarios
    "S1": ["Avvisami se domani fara molto freddo, devo mettere le piante al riparo",
            "Intendo quando la temperatura minima scende sotto i 2 gradi, mandami una notifica"],
    "S2": ["Quando ricevo un'email su una riunione aggiungila al calendario",
            "Solo se l'oggetto dell'email contiene la parola riunione o meeting"],
    "M1": ["Quando sblocco la porta fai partire la musica su Spotify",
            "Solo di sera, dopo le 18, non voglio musica la mattina"],
    "M2": ["Mandami un SMS quando c'e un avviso per il mio autobus",
            "Solo negli orari del tragitto, tra le 7 e le 9 di mattina, e solo per la linea 123"],
    "C1": ["Cambia il colore della lampada in base al livello di CO2",
            "Verde se il livello e basso, giallo se medio, rosso se alto"],
    "C2": ["Salva gli articoli del mio feed RSS su Dropbox",
            "Crea un file di testo col contenuto e scarica anche l'immagine se presente"],
    # Expert scenarios
    "E1": ["Cambia il colore e la luminosita della lampada LIFX in base alla CO2",
            "Usa l'indice di CO2: verde e luminoso se basso, giallo medio, rosso fioco se alto"],
    "E2": ["Quando un utente specifico pubblica un tweet, invialo su Telegram",
            "Solo se il tweet non contiene immagini, manda il testo e il link"],
    "E3": ["Salva i nuovi articoli del feed RSS su Dropbox come file di testo",
            "Includi titolo e contenuto nel file, e se c'e un'immagine scaricala separatamente"],
    "E4": ["Pubblica le mie foto Instagram sulla pagina Facebook",
            "Organizza per mese: usa il mese corrente come nome dell'album"],
    "E5": ["Mandami un SMS quando c'e un avviso per gli autobus",
            "Solo per la mia linea, includi il contenuto dell'avviso nel messaggio"],
    "E6": ["Quando un utente twitta, avvisami e salva il tweet su Feedly",
            "Pero non mandarmi notifiche di notte, tra le 23 e le 7 salva solo su Feedly"],
}

NON_EXPERT_ORDER = ["S1", "M1", "C1", "S2", "M2", "C2"]
EXPERT_ORDER = ["E2", "E1", "E3", "E5", "E4", "E6"]


def _is_non_expert(user_num: int) -> bool:
    return (user_num - 1) % 40 < 20


def _log(msg: str):
    try:
        print(f"  {msg}")
    except UnicodeEncodeError:
        print(f"  {msg.encode('ascii', errors='replace').decode('ascii')}")


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

async def _wait_rerun(page: Page, ms: int = 2000):
    await page.wait_for_timeout(ms)


async def _scroll_bottom(page: Page):
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(300)


async def _bypass_ngrok(page: Page):
    """Click 'Visit Site' if ngrok interstitial is showing."""
    try:
        btn = page.locator('button:has-text("Visit Site"), a:has-text("Visit Site")')
        await btn.first.wait_for(state="visible", timeout=3_000)
        await btn.first.click()
        _log("bypassed ngrok interstitial")
        await page.wait_for_timeout(2000)
    except Exception:
        pass


async def _dismiss_tutorial(page: Page):
    """Skip the tutorial overlay if present."""
    try:
        skip = page.locator("#tc-skip")
        await skip.wait_for(state="visible", timeout=5_000)
        _log("[tutorial] skipping...")
        try:
            await skip.click(timeout=5_000)
        except Exception:
            await page.evaluate('document.getElementById("tc-skip")?.click()')
        await _wait_rerun(page, 2500)
        await page.evaluate("""() => {
            document.getElementById('tutorial-spotlight')?.remove();
            document.getElementById('tutorial-callout')?.remove();
        }""")
        _log("[tutorial] done")
    except Exception:
        pass


async def _is_on_home(page: Page) -> bool:
    try:
        await page.locator(".sc-nav").first.wait_for(state="visible", timeout=1_500)
        return False
    except Exception:
        pass
    try:
        home = page.locator(
            'input[aria-label="Nome utente"], input[aria-label="Username"], '
            'button:has-text("Inizia lo studio"), button:has-text("Start the study")')
        await home.first.wait_for(state="visible", timeout=2_000)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core actions
# ---------------------------------------------------------------------------

async def send_intent(page: Page, text: str):
    form = page.locator('[data-testid="stForm"]')
    await form.first.wait_for(state="visible", timeout=15_000)
    textarea = form.locator("textarea").first
    await textarea.wait_for(state="visible", timeout=8_000)
    await textarea.click()
    await textarea.fill(text)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(200)
    submit = form.locator(
        '[data-testid="stFormSubmitButton"] button, '
        'button[kind="formSubmit"], button'
    ).first
    await submit.wait_for(state="visible", timeout=5_000)
    await submit.click()


async def wait_response(page: Page, timeout: int = 90_000) -> float:
    """Wait for orchestrator response. Returns latency in seconds."""
    t0 = time.monotonic()
    await page.wait_for_timeout(500)
    spinner = page.locator('[data-testid="stSpinner"], .stSpinner')
    try:
        await spinner.first.wait_for(state="visible", timeout=4_000)
        await spinner.first.wait_for(state="hidden", timeout=timeout)
    except Exception:
        try:
            await page.locator('[class*="st-key-eval_section"]').first.wait_for(
                state="visible", timeout=timeout)
        except Exception:
            await page.wait_for_timeout(2000)
    await page.wait_for_timeout(800)
    return time.monotonic() - t0


async def click_suggested_fields(page: Page):
    """Click suggested fields if present (condition B)."""
    await _scroll_bottom(page)
    try:
        btn = page.locator('[class*="st-key-use_fields_"] button')
        await btn.first.wait_for(state="visible", timeout=2_000)
        await btn.first.click()
        _log("[fields] selected all")
        await _wait_rerun(page, 1500)
        return
    except Exception:
        pass
    try:
        btns = page.locator('[class*="st-key-sug_f_"] button')
        count = await btns.count()
        if count > 0:
            for i in range(count):
                try:
                    await btns.nth(i).click(timeout=2_000)
                    await _wait_rerun(page, 1000)
                except Exception:
                    break
            _log(f"[fields] clicked {min(i+1, count)}")
    except Exception:
        pass


async def _js_click_radio(page: Page, container_class: str, label_text: str = ""):
    """Click a radio label via JS inside a container matching class pattern.
    If label_text is empty, clicks the first label found.
    """
    if label_text:
        clicked = await page.evaluate(f"""() => {{
            const containers = document.querySelectorAll('[class*="{container_class}"]');
            for (const c of containers) {{
                const labels = c.querySelectorAll('label');
                for (const l of labels) {{
                    if (l.textContent.trim().includes('{label_text}')) {{
                        l.click(); return true;
                    }}
                }}
            }}
            return false;
        }}""")
    else:
        clicked = await page.evaluate(f"""() => {{
            const containers = document.querySelectorAll('[class*="{container_class}"]');
            for (const c of containers) {{
                const label = c.querySelector('label');
                if (label) {{ label.click(); return true; }}
            }}
            return false;
        }}""")
    return clicked


async def fill_eval(page: Page, is_expert: bool = False):
    """Fill evaluation form with defaults (first option + confidence 3)."""
    await _scroll_bottom(page)

    # Wait for eval section to render
    eval_c = page.locator('[class*="st-key-eval_match"]')
    await eval_c.first.wait_for(state="visible", timeout=15_000)
    await page.wait_for_timeout(500)

    # Behavioral match — first option via JS
    await _js_click_radio(page, "st-key-eval_match")
    await page.wait_for_timeout(300)

    if is_expert:
        await _scroll_bottom(page)
        await page.wait_for_timeout(300)
        await _js_click_radio(page, "st-key-eval_code_correct", "yes")
        await page.wait_for_timeout(300)
        await _scroll_bottom(page)
        await _js_click_radio(page, "st-key-eval_conf_expert", "3")
    else:
        await _scroll_bottom(page)
        await page.wait_for_timeout(300)
        await _js_click_radio(page, "st-key-eval_conf", "3")

    await page.wait_for_timeout(300)


async def save_eval(page: Page):
    await _scroll_bottom(page)
    btn = page.locator('button:has-text("Salva valutazione"), button:has-text("Save evaluation")')
    await btn.first.wait_for(state="visible", timeout=8_000)
    try:
        await btn.first.click(timeout=5_000)
    except Exception:
        await btn.first.click(force=True, timeout=5_000)
    await _wait_rerun(page, 2000)


async def handle_questionnaire(page: Page) -> bool:
    """Handle unified TOAST+TLX+SUS questionnaire."""
    indicator = page.locator('[class*="st-key-toast_q"]')
    try:
        await indicator.first.wait_for(state="visible", timeout=5_000)
    except Exception:
        return False

    _log("[questionnaire] detected, submitting defaults...")
    await _scroll_bottom(page)

    submit = page.locator('[class*="st-key-questionnaire_submit"] button')
    try:
        await submit.first.wait_for(state="visible", timeout=5_000)
    except Exception:
        submit = page.locator(
            'button:has-text("Invia e continua"), button:has-text("Submit and continue"), '
            'button:has-text("Invia questionario finale"), button:has-text("Submit final questionnaire")')
        await submit.first.wait_for(state="visible", timeout=3_000)

    await submit.first.scroll_into_view_if_needed()
    await submit.first.click()
    await _wait_rerun(page, 3000)
    _log("[questionnaire] submitted")
    return True


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

async def run_test(url: str, user_id: str, headless: bool = False):
    user_num = int(user_id.replace("user_", ""))
    is_expert = not _is_non_expert(user_num)
    user_type = "expert" if is_expert else "non_expert"
    scenario_order = EXPERT_ORDER if is_expert else NON_EXPERT_ORDER

    _log(f"{'='*55}")
    _log(f"NL2TAP Remote Test — {user_id} ({user_type})")
    _log(f"URL: {url}")
    _log(f"Scenarios: {' → '.join(scenario_order)}")
    _log(f"{'='*55}\n")

    t_total = time.monotonic()
    latencies = []
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        # --- Navigate ---
        _log("navigating...")
        await page.goto(url, wait_until="domcontentloaded")
        await _bypass_ngrok(page)
        await page.wait_for_selector(
            '[data-testid="stAppViewContainer"]',
            state="visible", timeout=30_000)
        await page.wait_for_timeout(1000)

        # --- Login ---
        _log("logging in...")
        user_input = page.locator(
            'input[aria-label="Nome utente"], input[aria-label="Username"]')
        await user_input.first.wait_for(state="visible", timeout=10_000)
        await user_input.first.fill(user_id)

        pw_input = page.locator(
            'input[aria-label="Codice di accesso"], input[aria-label="Access code"]')
        await pw_input.first.fill(ACCESS_CODE)

        login_btn = page.locator('button:has-text("Accedi"), button:has-text("Log in")')
        await login_btn.first.click()
        await _wait_rerun(page, 3000)

        # --- Start study ---
        studio = page.locator('.sc-nav, textarea, [data-testid="stForm"]')
        try:
            await studio.first.wait_for(state="visible", timeout=3_000)
            _log("already on Studio")
        except Exception:
            start_btn = page.locator(
                'button:has-text("Inizia lo studio"), button:has-text("Start the study"), '
                'button:has-text("Riprendi lo studio"), button:has-text("Resume the study")')
            await start_btn.first.wait_for(state="visible", timeout=15_000)
            await start_btn.first.click()
            _log("clicked Start")
            await _wait_rerun(page, 3000)

        await page.wait_for_selector(
            '.sc-nav, textarea, [data-testid="stForm"]',
            state="visible", timeout=15_000)
        _log("Studio loaded")

        await _dismiss_tutorial(page)

        # --- Scenarios ---
        sc_done = 0
        for sc_code in scenario_order:
            if await _is_on_home(page):
                _log("redirected to Home — study complete")
                break

            # Wait for chat form
            try:
                await page.locator('[data-testid="stForm"]').first.wait_for(
                    state="visible", timeout=10_000)
            except Exception:
                # Maybe questionnaire
                if await handle_questionnaire(page):
                    await _wait_rerun(page, 2000)
                    if await _is_on_home(page):
                        _log("redirected to Home — study complete")
                        break
                    try:
                        await page.locator('[data-testid="stForm"]').first.wait_for(
                            state="visible", timeout=8_000)
                    except Exception:
                        _log(f"no form for {sc_code}, stopping")
                        break

            t_sc = time.monotonic()
            _log(f"\n--- {sc_code} ({sc_done+1}/{len(scenario_order)}) ---")

            intents = INTENTS.get(sc_code, [])
            ok = True
            try:
                for i, intent in enumerate(intents):
                    _log(f"  intent {i+1}/{len(intents)}: sending...")
                    await send_intent(page, intent)
                    latency = await wait_response(page)
                    latencies.append(latency)
                    _log(f"  intent {i+1}/{len(intents)}: received ({latency:.1f}s)")

                    await click_suggested_fields(page)

                _log(f"  filling eval...")
                await fill_eval(page, is_expert=is_expert)
                await save_eval(page)
                _log(f"  eval saved")

            except Exception as e:
                err = str(e).split("\n")[0][:120]
                _log(f"  FAIL: {err}")
                ok = False

            elapsed = time.monotonic() - t_sc
            tag = "OK" if ok else "FAIL"
            results.append((sc_code, tag, elapsed))
            _log(f"  {sc_code} [{tag} {elapsed:.0f}s]")
            sc_done += 1

            # Post-eval: check for questionnaire
            await page.wait_for_timeout(3000)
            if await handle_questionnaire(page):
                await _wait_rerun(page, 2000)
                if await _is_on_home(page):
                    _log("redirected to Home — study complete")
                    break

        # --- Report ---
        total_time = time.monotonic() - t_total
        n_ok = sum(1 for _, t, _ in results if t == "OK")

        _log(f"\n{'='*55}")
        _log(f"RESULTS — {user_id} ({user_type})")
        _log(f"{'='*55}")
        for code, tag, elapsed in results:
            _log(f"  {code:>3s}  [{tag} {elapsed:.0f}s]")

        _log(f"\n  Passed: {n_ok}/{len(results)}")
        _log(f"  Total:  {total_time:.0f}s")

        if latencies:
            latencies.sort()
            n = len(latencies)
            _log(f"\n  SERVER LATENCY ({n} requests)")
            _log(f"  avg: {sum(latencies)/n:.1f}s  |  "
                 f"p50: {latencies[n//2]:.1f}s  |  "
                 f"p90: {latencies[int(n*0.9)]:.1f}s")
            _log(f"  min: {latencies[0]:.1f}s  |  max: {latencies[-1]:.1f}s")

        _log("")

        if not headless:
            _log("Browser open. Press ENTER to close...")
            try:
                await asyncio.get_event_loop().run_in_executor(None, input)
            except EOFError:
                await asyncio.sleep(5)

        await browser.close()

    return n_ok == len(results)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="NL2TAP standalone remote smoke-test")
    parser.add_argument("--url", required=True,
                        help="App URL (ngrok or localhost)")
    parser.add_argument("--user", default="user_9001",
                        help="User ID (default: user_9001)")
    parser.add_argument("--headless", action="store_true",
                        help="Run without visible browser")
    args = parser.parse_args()

    ok = asyncio.run(run_test(
        url=args.url.rstrip("/"),
        user_id=args.user,
        headless=args.headless,
    ))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
