from collections import deque

from .planificador import round_robin
from .procesos import crear_procesos


def main():
    datos = deque(maxlen=50)
    round_robin(crear_procesos(datos))
