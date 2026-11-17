import os
import re
import tempfile

from app.models.comprobante import Comprobante


def _nombre_seguro(texto: str) -> str:
    """Evita caracteres invalidos en nombres de archivo."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(texto)).strip().strip(".")
    return limpio or "sin_dato"


class LocalStorage:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.dir_pdf = os.path.join(output_dir, "pdfs")
        self.dir_xml = os.path.join(output_dir, "xmls")
        os.makedirs(self.dir_pdf, exist_ok=True)
        os.makedirs(self.dir_xml, exist_ok=True)

    def nombre_base(self, cpe: Comprobante) -> str:
        return "_".join(
            _nombre_seguro(parte) for parte in (cpe.ruc, cpe.serie, cpe.numero)
        )

    def path_pdf(self, cpe: Comprobante) -> str:
        return os.path.join(self.dir_pdf, f"{self.nombre_base(cpe)}.pdf")

    def path_xml(self, cpe: Comprobante) -> str:
        return os.path.join(self.dir_xml, f"{self.nombre_base(cpe)}.xml")

    def existe_pdf(self, cpe: Comprobante) -> bool:
        return os.path.exists(self.path_pdf(cpe))

    def existe_xml(self, cpe: Comprobante) -> bool:
        return os.path.exists(self.path_xml(cpe))

    def guardar(self, cpe: Comprobante, tipo: str, data: bytes):
        path = self.path_pdf(cpe) if tipo == "pdf" else self.path_xml(cpe)
        # Escritura atomica: evita archivos truncados si el proceso se corta
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
