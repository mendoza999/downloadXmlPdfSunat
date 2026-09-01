from playwright.sync_api import sync_playwright
import logging

logger = logging.getLogger(__name__)

def obtener_token_automatico(ruc: str, usuario: str, clave: str) -> str:
    logger.info("Iniciando navegador virtual...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            slow_mo=500,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."
        )
        main_page = context.new_page()
        token_capturado = {"valor": None}

        def interceptar(request):
            headers = request.headers
            if "authorization" in headers and "Bearer" in headers["authorization"]:
                if not token_capturado["valor"]:
                    token_capturado["valor"] = headers["authorization"].replace("Bearer ", "").strip()
                    logger.info("✅ Token interceptado.")

        context.on("request", interceptar)

        try:
            main_page.goto("https://www.sunat.gob.pe/sol.html", wait_until="domcontentloaded", timeout=45000)
            with context.expect_page() as new_page_info:
                main_page.click("a[href*='tramiteConsulta']")
            app_page = new_page_info.value
            app_page.wait_for_load_state("domcontentloaded")
            app_page.wait_for_selector("#txtRuc", timeout=30000)
            app_page.fill("#txtRuc", ruc)
            app_page.fill("#txtUsuario", usuario)
            app_page.fill("#txtContrasena", clave)
            app_page.click("#btnAceptar")
            app_page.wait_for_url("**/MenuInternet.htm**", timeout=30000)
            logger.info("Login exitoso.")

            # Cerrar modales
            try:
                campana = app_page.locator("#divModalCampana")
                campana.wait_for(state="visible", timeout=5000)
                ifr_vce = app_page.frame_locator("iframe[name='ifrVCE']")
                for selector in [
                    "#modalInformativoValidacionDatos #btnFinalizarValidacionDatos",
                    "#modalInformativoSecundario #btnFinalizarValidacionDatos"
                ]:
                    btn = ifr_vce.locator(selector)
                    try:
                        btn.wait_for(state="visible", timeout=3000)
                        btn.dispatch_event("click")
                        app_page.wait_for_timeout(1000)
                    except Exception:
                        continue
                campana.wait_for(state="hidden", timeout=5000)
                logger.info("Modales cerrados.")
            except Exception:
                logger.info("Sin modales.")

            # Navegación si falta token
            if not token_capturado["valor"]:
                app_page.click("#divOpcionServicio2", force=True)
                app_page.click("#nivel1_11", force=True)
                app_page.click("#nivel2_11_38", force=True)
                app_page.click("#nivel3_11_38_1", force=True)
                app_page.click("#nivel4_11_38_1_1_1", force=True)
                frame_facturas = app_page.frame_locator("iframe#iframeApplication")
                frame_facturas.locator("input[name='rucEmisor']").wait_for(state="visible", timeout=30000)
                app_page.wait_for_timeout(3000)

            if not token_capturado["valor"]:
                token_storage = app_page.evaluate('''() => {
                    return sessionStorage.getItem("token") || localStorage.getItem("access_token");
                }''')
                if token_storage:
                    token_capturado["valor"] = token_storage
        except Exception as e:
            logger.error(f"Error en login: {e}")
            main_page.wait_for_timeout(15000)
        finally:
            browser.close()

        if not token_capturado["valor"]:
            raise Exception("No se pudo obtener el token.")
        return token_capturado["valor"]