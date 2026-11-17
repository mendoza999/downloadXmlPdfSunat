"""Modelo de comprobante y lectura del archivo Excel.

El Excel puede tener los datos en columnas distintas segun el origen del
reporte. Por eso el lector ubica los encabezados por nombre en lugar de
depender de letras fijas, y solo usa la posicion (G, H, I, J) como
respaldo cuando el archivo no tiene encabezados reconocibles.
"""

import logging
import math
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Codigos SUNAT para el tipo de comprobante
TIPO_DOC_MAP: Dict[str, str] = {
    "1": "01",
    "01": "01",
    "factura": "01",
    "facturas": "01",
    "3": "03",
    "03": "03",
    "boleta": "03",
    "boletas": "03",
    "7": "07",
    "07": "07",
    "notacredito": "07",
    "notadecredito": "07",
    "8": "08",
    "08": "08",
    "notadebito": "08",
    "notadedebito": "08",
    "9": "09",
    "09": "09",
    "guiaremision": "09",
    "guiaderemision": "09",
}

# Nombres de encabezado aceptados para cada campo
HEADER_ALIASES: Dict[str, Tuple[str, ...]] = {
    "tipo": (
        "tipo",
        "tipo doc",
        "tipo documento",
        "tipo de documento",
        "tipo comprobante",
        "tipo de comprobante",
        "tipo cdp",
        "cod tipo",
        "codigo tipo",
        "cod tipo comprobante",
    ),
    "serie": ("serie", "serie comprobante", "serie documento", "serie cdp"),
    "numero": (
        "numero",
        "numero comprobante",
        "numero de comprobante",
        "numero doc",
        "nro",
        "nro comprobante",
        "nro de comprobante",
        "num",
        "correlativo",
        "numero cdp",
    ),
    "ruc": (
        "ruc",
        "ruc emisor",
        "ruc del emisor",
        "ruc proveedor",
        "ruc_emisor",
        "rucemisor",
        "ruc cdp",
    ),
}

# Columnas por posicion (base 0) usadas cuando no hay encabezados:
# G = tipo, H = serie, I = numero, J = RUC emisor
COLUMNAS_POR_DEFECTO: Dict[str, int] = {
    "tipo": 6,
    "serie": 7,
    "numero": 8,
    "ruc": 9,
}


@dataclass
class Comprobante:
    ruc: str
    tipo: str
    serie: str
    numero: str
    fila: int

    @property
    def nombre_base(self) -> str:
        return f"{self.ruc}_{self.serie}_{self.numero}"

    def __str__(self) -> str:  # pragma: no cover - utilidad de logs
        return f"{self.tipo}-{self.serie}-{self.numero} (RUC {self.ruc}, fila {self.fila})"


def _sin_acentos(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", valor)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def _normalizar_texto(valor: object) -> str:
    """Convierte una celda a texto limpio (sin NaN, sin '.0' sobrante)."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        if math.isnan(valor):
            return ""
        if valor.is_integer():
            return str(int(valor))
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    return str(valor).strip()


def _normalizar_header(valor: object) -> str:
    texto = _sin_acentos(_normalizar_texto(valor).lower())
    texto = "".join(c if c.isalnum() else " " for c in texto)
    return " ".join(texto.split())


def _normalizar_tipo(valor: object) -> str:
    """Devuelve el codigo SUNAT de dos digitos (01, 03, 07, 08, 09)."""
    texto = _normalizar_texto(valor).lower()
    if not texto:
        return ""
    compacto = "".join(c for c in _sin_acentos(texto) if c.isalnum())
    if compacto in TIPO_DOC_MAP:
        return TIPO_DOC_MAP[compacto]
    if compacto.isdigit():
        return compacto.zfill(2)
    return _normalizar_texto(valor).upper()


def _normalizar_ruc(valor: object) -> str:
    texto = _normalizar_texto(valor)
    # A veces el RUC viene con guiones o espacios: 20-61414103-5
    return "".join(c for c in texto if c.isdigit())


def crear_comprobante(
    tipo_doc: object,
    serie: object,
    numero: object,
    ruc_emisor: object,
    fila: int = 0,
) -> Comprobante:
    """Construye un comprobante a partir de parametros sueltos (API).

    Normaliza y valida los mismos campos que se leen desde el Excel. Lanza
    ``ValueError`` con un mensaje claro si falta algun dato o el RUC no es
    valido.
    """
    tipo = _normalizar_tipo(tipo_doc)
    serie = _normalizar_texto(serie).upper().replace(" ", "")
    numero = _normalizar_texto(numero).replace(" ", "")
    ruc = _normalizar_ruc(ruc_emisor)

    problemas: List[str] = []
    if not tipo:
        problemas.append("tipo_doc")
    elif not (tipo.isdigit() and len(tipo) == 2):
        problemas.append(
            f"tipo_doc '{tipo}' no es valido (use codigos de 2 digitos: 01, 03, 07, 08, 09)"
        )
    if not serie:
        problemas.append("serie")
    if not numero:
        problemas.append("numero")
    if not ruc:
        problemas.append("ruc_emisor")
    elif len(ruc) != 11:
        problemas.append(f"ruc_emisor '{ruc}' no tiene 11 digitos")

    if problemas:
        raise ValueError("Datos del comprobante invalidos: " + ", ".join(problemas))

    return Comprobante(ruc=ruc, tipo=tipo, serie=serie, numero=numero, fila=fila)


def _detectar_columnas(
    df: pd.DataFrame,
) -> Tuple[Optional[int], Dict[str, int]]:
    """Busca la fila de encabezados y el indice de columna de cada campo."""
    limite = min(20, len(df))
    for fila in range(limite):
        valores = [_normalizar_header(v) for v in df.iloc[fila].tolist()]
        encontrados: Dict[str, int] = {}
        for campo, alias in HEADER_ALIASES.items():
            for columna, valor in enumerate(valores):
                if valor in alias and campo not in encontrados:
                    encontrados[campo] = columna
                    break
        if len(encontrados) == len(HEADER_ALIASES):
            return fila, encontrados
    return None, dict(COLUMNAS_POR_DEFECTO)


def leer_excel(excel_path: str) -> List[Comprobante]:
    """Lee el Excel y devuelve la lista de comprobantes validos.

    Los encabezados se detectan por nombre ("Tipo", "Serie", "Numero",
    "RUC Emisor", entre otras variantes). Si no se encuentran, se asume la
    estructura clasica: columnas G, H, I y J.
    """
    try:
        df = pd.read_excel(excel_path, header=None, dtype=object)
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ValueError(
            "Falta la dependencia openpyxl para leer archivos .xlsx. "
            "Ejecute: pip install openpyxl"
        ) from exc
    except Exception as exc:
        raise ValueError(f"No se pudo leer el archivo Excel '{excel_path}': {exc}") from exc

    if df.empty:
        raise ValueError("El archivo Excel esta vacio.")

    fila_header, columnas = _detectar_columnas(df)
    inicio_datos = 0 if fila_header is None else fila_header + 1

    faltantes = [campo for campo in ("tipo", "serie", "numero", "ruc") if campo not in columnas]
    if faltantes:
        raise ValueError(
            "No se pudieron identificar las columnas del Excel. "
            "Se esperan encabezados como: Tipo, Serie, Numero, RUC Emisor."
        )

    comprobantes: List[Comprobante] = []
    vistos = set()
    errores: List[str] = []

    for posicion in range(inicio_datos, len(df)):
        fila_excel = posicion + 1  # 1-based, igual que ve el usuario en Excel
        fila = df.iloc[posicion]

        def celda(campo: str) -> object:
            indice = columnas[campo]
            if indice >= len(fila):
                return None
            return fila.iloc[indice]

        tipo = _normalizar_tipo(celda("tipo"))
        serie = _normalizar_texto(celda("serie")).upper().replace(" ", "")
        numero = _normalizar_texto(celda("numero")).replace(" ", "")
        ruc = _normalizar_ruc(celda("ruc"))

        # Fila totalmente vacia: se ignora sin reportar error
        if not any((tipo, serie, numero, ruc)):
            continue

        problemas = []
        if not tipo:
            problemas.append("tipo")
        if not serie:
            problemas.append("serie")
        if not numero:
            problemas.append("numero")
        if not ruc:
            problemas.append("RUC emisor")
        elif len(ruc) != 11:
            problemas.append(f"RUC '{ruc}' no tiene 11 digitos")

        if problemas:
            errores.append(f"fila {fila_excel}: {', '.join(problemas)}")
            continue

        clave = (ruc, tipo, serie, numero)
        if clave in vistos:
            logger.warning("Comprobante duplicado en fila %s: %s-%s", fila_excel, serie, numero)
            continue
        vistos.add(clave)

        comprobantes.append(
            Comprobante(ruc=ruc, tipo=tipo, serie=serie, numero=numero, fila=fila_excel)
        )

    if errores:
        logger.warning(
            "Se omitieron %s fila(s) con datos invalidos: %s",
            len(errores),
            "; ".join(errores[:10]),
        )

    if not comprobantes:
        detalle = f" Detalle: {'; '.join(errores[:10])}" if errores else ""
        raise ValueError(
            "No se encontraron comprobantes validos en el Excel." + detalle
        )

    logger.info(
        "Excel leido: %s comprobantes validos (encabezado en fila %s, columnas %s).",
        len(comprobantes),
        (fila_header + 1) if fila_header is not None else "N/D",
        columnas,
    )
    return comprobantes
