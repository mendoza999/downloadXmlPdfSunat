import logging
import time
from typing import Optional
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from app.core import config

logger = logging.getLogger(__name__)

MENU_HOST_PREFIX = "e-menu"


class SunatAuthError(RuntimeError):
    """Error controlado durante el login en SUNAT."""


def obtener_token_automatico(ruc: str, usuario: str, clave: str) -> str:
    """Inicia sesión en SUNAT con Playwright y devuelve el token Bearer.

    Lanza SunatAuthError con un mensaje claro si no se puede autenticar.
    """
    if not all((ruc, usuario, clave)):
        raise SunatAuthError(
            "Credenciales SUNAT incompletas: defina SUNAT_RUC, SUNAT_USUARIO y SUNAT_CLAVE."
        )

    timeout = config.SUNAT_TIMEOUT_MS
    logger.info("Iniciando navegador virtual...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.SUNAT_HEADLESS,
            slow_mo=config.SUNAT_SLOW_MO,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        main_page = context.new_page()
        token_capturado = {"valor": None}
        error_login: Optional[Exception] = None

        def interceptar(request):
            headers = request.headers
            authorization = headers.get("authorization") or headers.get("Authorization")
            if authorization and "Bearer" in authorization and not token_capturado["valor"]:
                token_capturado["valor"] = authorization.replace("Bearer", "").strip()
                logger.info("✅ Token interceptado.")

        context.on("request", interceptar)

        try:
            main_page.goto(
                "https://www.sunat.gob.pe/sol.html",
                wait_until="domcontentloaded",
                timeout=timeout,
            )
            with context.expect_page(timeout=timeout) as new_page_info:
                main_page.click("a[href*='tramiteConsulta']")
            app_page = new_page_info.value
            app_page.wait_for_load_state("domcontentloaded")

            # El portal redirige al formulario OAuth; esperamos a que el JS esté
            # enganchado al botón antes de escribir (si no, el click no hace nada).
            app_page.wait_for_selector("#txtRuc", state="visible", timeout=timeout)
            app_page.wait_for_load_state("load", timeout=timeout)
            app_page.wait_for_function(
                """() => {
                    const btn = document.getElementById('btnAceptar');
                    if (!window.jQuery || !btn) return false;
                    const eventos = jQuery._data(btn, 'events');
                    return !!(eventos && eventos.click);
                }""",
                timeout=timeout,
            )

            app_page.fill("#txtRuc", ruc)
            app_page.fill("#txtUsuario", usuario)
            app_page.fill("#txtContrasena", clave)
            app_page.click("#btnAceptar")

            _esperar_resultado_login(app_page, timeout)
            logger.info("Login exitoso.")

            _cerrar_modales(app_page)

            # Navegación si todavía no se capturó el token
            if not token_capturado["valor"]:
                _abrir_consulta_comprobantes(app_page, timeout, token_capturado)

            if not token_capturado["valor"]:
                token_storage = app_page.evaluate(
                    """() => sessionStorage.getItem("token")
                        || localStorage.getItem("access_token")
                        || sessionStorage.getItem("access_token")"""
                )
                if token_storage:
                    token_capturado["valor"] = token_storage
        except SunatAuthError as exc:
            error_login = exc
            logger.error("%s", exc)
        except Exception as exc:
            error_login = exc
            logger.error("Error en login: %s", exc, exc_info=True)
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    if not token_capturado["valor"]:
        if error_login:
            raise SunatAuthError(f"No se pudo obtener el token de SUNAT: {error_login}")
        raise SunatAuthError(
            "No se pudo obtener el token de SUNAT. El portal puede haber cambiado o "
            "las credenciales son incorrectas."
        )

    return token_capturado["valor"]


def obtener_token_con_reintentos(
    ruc: str, usuario: str, clave: str, intentos: int = None
) -> str:
    """Reintenta el login ante fallos de red/timeout, no ante credenciales."""
    intentos = intentos or config.SUNAT_LOGIN_INTENTOS
    ultimo_error: Optional[Exception] = None

    for intento in range(1, intentos + 1):
        try:
            return obtener_token_automatico(ruc, usuario, clave)
        except SunatAuthError as exc:
            mensaje = str(exc).lower()
            if "captcha" in mensaje or "rechazado" in mensaje or "credenciales" in mensaje:
                raise
            ultimo_error = exc
        except Exception as exc:  # errores de Playwright / red
            ultimo_error = exc

        if intento < intentos:
            espera = config.SUNAT_LOGIN_ESPERA_SEG
            logger.warning(
                "Intento de login %s/%s falló (%s). Reintentando en %s s...",
                intento,
                intentos,
                ultimo_error,
                espera,
            )
            time.sleep(espera)

    raise SunatAuthError(f"No se pudo iniciar sesión en SUNAT: {ultimo_error}")


RUTA_MENU_CONSULTA = (
    "#nivel1_11",  # Comprobantes de pago
    "#nivel2_11_38",  # Comprobantes de Pago
    "#nivel3_11_38_1",  # Consulta de Comprobantes de Pago
    "#nivel4_11_38_1_1_1",  # Nueva Consulta de comprobantes de pago
)


def _click_menu(app_page, selector: str, timeout_ms: int) -> None:
    """Hace clic en una opción del menú SOL esperando a que esté visible."""
    locator = app_page.locator(selector).first
    if not locator.count():
        raise SunatAuthError(f"No se encontró la opción del menú {selector}.")
    locator.wait_for(state="visible", timeout=timeout_ms)
    locator.click()
    # El menú carga los subniveles por AJAX; damos tiempo a que aparezcan
    app_page.wait_for_timeout(1200)


def _abrir_consulta_comprobantes(app_page, timeout_ms: int, token_capturado: dict) -> None:
    """Navega hasta 'Nueva Consulta de comprobantes de pago'.

    Al abrir el módulo, el navegador llama a la API de SUNAT con el token
    Bearer, que es interceptado por el listener de requests.
    """
    try:
        for selector in RUTA_MENU_CONSULTA:
            _click_menu(app_page, selector, timeout_ms)
    except Exception as exc:
        logger.warning("No se pudo navegar al módulo de facturas: %s", exc)
        return

    # Esperar a que el iframe del módulo haga las primeras llamadas a la API
    limite = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < limite and not token_capturado["valor"]:
        app_page.wait_for_timeout(500)

    if token_capturado["valor"]:
        return

    # Último intento: esperar el campo de consulta dentro del iframe
    try:
        frame_facturas = app_page.frame_locator("iframe#iframeApplication")
        frame_facturas.locator("input[name='rucEmisor']").wait_for(
            state="visible", timeout=timeout_ms
        )
        app_page.wait_for_timeout(2000)
    except Exception as exc:
        logger.warning("El módulo de consulta no cargó completamente: %s", exc)


def _esperar_resultado_login(app_page, timeout_ms: int) -> None:
    """Espera el resultado del login: éxito, error visible o captcha."""
    limite = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < limite:
        if _en_menu_principal(app_page.url):
            return

        captcha_visible = False
        try:
            captcha_visible = app_page.locator("#txtCaptcha").is_visible(timeout=500)
        except Exception:
            captcha_visible = False
        if captcha_visible:
            raise SunatAuthError(
                "SUNAT solicita un CAPTCHA porque hubo varios intentos de login fallidos. "
                "Ingrese manualmente al portal SOL una vez con estas credenciales para "
                "reiniciar el contador y luego vuelva a ejecutar la descarga."
            )

        mensaje = _mensaje_error_login(app_page)
        if mensaje:
            raise SunatAuthError(f"Login en SUNAT rechazado. {mensaje}")

        try:
            app_page.wait_for_timeout(500)
        except Exception:
            # La página pudo navegar mientras esperábamos: reevaluamos la URL
            if _en_menu_principal(app_page.url):
                return

    raise SunatAuthError(
        "Tiempo de espera agotado durante el login en SUNAT. "
        "Puede ser lentitud del portal o credenciales incorrectas. "
        "Verifique RUC/usuario/clave e intente nuevamente."
    )


def _en_menu_principal(url: str) -> bool:
    partes = urlparse(url)
    host = (partes.hostname or "").lower()
    ruta = (partes.path or "").lower()
    return (
        host.startswith(MENU_HOST_PREFIX)
        and host.endswith("sunat.gob.pe")
        and "menu" in ruta
        and "autentica" not in ruta
    )


def _cerrar_modales(app_page):
    """Cierra los modales informativos que bloquean la navegación."""
    try:
        campana = app_page.locator("#divModalCampana")
        campana.wait_for(state="visible", timeout=5000)
        ifr_vce = app_page.frame_locator("iframe[name='ifrVCE']")
        for selector in [
            "#modalInformativoValidacionDatos #btnFinalizarValidacionDatos",
            "#modalInformativoSecundario #btnFinalizarValidacionDatos",
        ]:
            btn = ifr_vce.locator(selector)
            try:
                btn.wait_for(state="visible", timeout=3000)
                btn.dispatch_event("click")
                app_page.wait_for_timeout(1000)
            except Exception:
                continue
        try:
            campana.wait_for(state="hidden", timeout=5000)
        except Exception:
            pass
        logger.info("Modales cerrados.")
    except Exception:
        logger.info("Sin modales.")


def _mensaje_error_login(app_page) -> str:
    """Devuelve el texto de error visible del formulario de login, si existe."""
    for selector in ("#spanMensajeError", "#divMensajeError", "#lblMensaje", ".mensajeError"):
        try:
            locator = app_page.locator(selector).first
            if not locator.count():
                continue
            contenedor = locator
            if selector == "#spanMensajeError":
                contenedor = app_page.locator("#divMensajeError").first
            if contenedor.count() and contenedor.is_visible(timeout=500):
                texto = (locator.inner_text() or "").strip()
                if texto:
                    return f"Mensaje del portal: {texto}"
        except Exception:
            continue
    return ""
