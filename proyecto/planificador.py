from collections import deque
import time

from .configuracion import MOSTRAR_ESTADOS, QUANTUM, SEGUNDOS_POR_IMPRESION
from .procesos import Estado


def admitir(procesos, cola_listos):
    print("== Admisión de procesos ==")
    for proceso in procesos:
        print(f"  PID {proceso.pid} {proceso.nombre:<10}: {proceso.estado.name}")
        proceso.estado = Estado.LISTO
        cola_listos.append(proceso)
    print(f"  Cola de listos: {[p.nombre for p in cola_listos]}\n")


def round_robin(procesos, quantum=QUANTUM):
    cola_listos = deque()
    cola_bloqueados = []
    admitir(procesos, cola_listos)

    print(
        f"Sistema: Windows | impresión cada {SEGUNDOS_POR_IMPRESION}s "
        "| Ctrl+C para salir\n"
    )

    try:
        while True:
            ahora = time.monotonic()
            siguen_bloqueados = []
            for proceso in cola_bloqueados:
                if proceso.despertar_en <= ahora:
                    proceso.estado = Estado.LISTO
                    cola_listos.append(proceso)
                else:
                    siguen_bloqueados.append(proceso)
            cola_bloqueados = siguen_bloqueados

            for _ in range(len(cola_listos)):
                proceso = cola_listos.popleft()
                proceso.estado = Estado.EJECUTANDO
                if MOSTRAR_ESTADOS:
                    print(f"  >> PID {proceso.pid} {proceso.nombre}: EJECUTANDO")

                senal = next(proceso.generador)
                proceso.turnos_ejecutados += 1

                if senal == "BLOQUEAR":
                    proceso.estado = Estado.BLOQUEADO
                    proceso.despertar_en = (
                        time.monotonic() + SEGUNDOS_POR_IMPRESION
                    )
                    cola_bloqueados.append(proceso)
                else:
                    proceso.estado = Estado.LISTO
                    cola_listos.append(proceso)

            espera = quantum
            if cola_bloqueados:
                proximo_despertar = min(p.despertar_en for p in cola_bloqueados)
                espera = min(
                    espera,
                    max(0, proximo_despertar - time.monotonic()),
                )
            time.sleep(espera)
    except KeyboardInterrupt:
        print("\n== Finalizando procesos ==")
        for proceso in procesos:
            proceso.generador.close()
            proceso.estado = Estado.TERMINADO
            print(
                f"  PID {proceso.pid} {proceso.nombre:<10}: TERMINADO "
                f"({proceso.turnos_ejecutados} turnos ejecutados)"
            )
        print("\nMonitor detenido.")
