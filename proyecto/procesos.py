from dataclasses import dataclass
from enum import Enum, auto
from typing import Generator

from .impresor import proceso_impresor
from .recolector import proceso_recolector


class Estado(Enum):
    NUEVO = auto()
    LISTO = auto()
    EJECUTANDO = auto()
    BLOQUEADO = auto()
    TERMINADO = auto()


@dataclass
class PCB:
    """Datos del proceso que necesita el planificador."""

    pid: int
    nombre: str
    generador: Generator[str, None, None]
    estado: Estado = Estado.NUEVO
    turnos_ejecutados: int = 0
    despertar_en: float = 0.0


def crear_procesos(cola_datos):
    return [
        PCB(1, "Recolector", proceso_recolector(cola_datos)),
        PCB(2, "Impresor", proceso_impresor(cola_datos)),
    ]
