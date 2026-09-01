from dataclasses import dataclass
from typing import List
import pandas as pd

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

def leer_excel(excel_path: str) -> List[Comprobante]:
    """Lee el Excel y devuelve una lista de comprobantes."""
    df = pd.read_excel(excel_path, usecols="G,H,J,M", dtype=str, header=0)
    df.columns = ["tipo_doc", "serie", "numero", "ruc_emisor"]

    comprobantes = []
    for index, row in df.iterrows():
        tipo_raw = str(row["tipo_doc"]).strip()
        comprobantes.append(Comprobante(
            ruc=str(row["ruc_emisor"]).strip(),
            tipo="01" if tipo_raw == "1" else tipo_raw.zfill(2),
            serie=str(row["serie"]).strip().upper(),
            numero=str(row["numero"]).strip(),
            fila=index + 2,
        ))
    return comprobantes