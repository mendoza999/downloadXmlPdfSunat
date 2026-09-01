import os
from app.models.comprobante import Comprobante

class LocalStorage:
    def __init__(self, output_dir: str):
        self.dir_pdf = os.path.join(output_dir, "pdfs")
        self.dir_xml = os.path.join(output_dir, "xmls")
        os.makedirs(self.dir_pdf, exist_ok=True)
        os.makedirs(self.dir_xml, exist_ok=True)

    def path_pdf(self, cpe: Comprobante) -> str:
        return os.path.join(self.dir_pdf, f"{cpe.nombre_base}.pdf")

    def path_xml(self, cpe: Comprobante) -> str:
        return os.path.join(self.dir_xml, f"{cpe.nombre_base}.xml")

    def existe_pdf(self, cpe: Comprobante) -> bool:
        return os.path.exists(self.path_pdf(cpe))

    def existe_xml(self, cpe: Comprobante) -> bool:
        return os.path.exists(self.path_xml(cpe))

    def guardar(self, cpe: Comprobante, tipo: str, data: bytes):
        path = self.path_pdf(cpe) if tipo == "pdf" else self.path_xml(cpe)
        with open(path, "wb") as f:
            f.write(data)