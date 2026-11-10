"""Recolección asíncrona de zonas térmicas ACPI en Windows."""

import base64
import json
import math
import shutil
import subprocess
import time
from datetime import datetime

from .configuracion import (
    INTERVALO_RECOLECCION,
    REINTENTO_SIN_LECTURA,
    TIEMPO_MAXIMO_LECTURA,
)


_CONSULTA_POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $zonas = @(Get-CimInstance -Namespace 'root/wmi' `
        -ClassName 'MSAcpi_ThermalZoneTemperature' | ForEach-Object {
        [pscustomobject]@{
            instancia = [string]$_.InstanceName
            temperatura_raw = $_.CurrentTemperature
        }
    })
    [pscustomobject]@{ ok = $true; zonas = $zonas } |
        ConvertTo-Json -Compress -Depth 4
} catch {
    [pscustomobject]@{ ok = $false; error = $_.Exception.Message } |
        ConvertTo-Json -Compress
    exit 1
}
"""


def _crear_muestra(estado, sensores=(), error=None, duracion=None):
    return {
        "capturada_en": datetime.now().astimezone(),
        "estado": estado,
        "sensores": list(sensores),
        "error": error,
        "duracion_s": round(duracion, 3) if duracion is not None else None,
    }


def iniciar_lectura_temperaturas():
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise FileNotFoundError("No se encontró PowerShell en PATH.")

    comando_codificado = base64.b64encode(
        _CONSULTA_POWERSHELL.encode("utf-16le")
    ).decode("ascii")
    argumentos = [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        comando_codificado,
    ]
    return subprocess.Popen(
        argumentos,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def convertir_temperaturas(salida):
    """Convierte décimas de Kelvin de WMI a lecturas Celsius identificadas."""
    try:
        respuesta = json.loads(salida.lstrip("\ufeff"))
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("PowerShell devolvió una respuesta no válida.") from error

    if not isinstance(respuesta, dict):
        raise ValueError("La respuesta de PowerShell no tiene el formato esperado.")
    if not respuesta.get("ok"):
        raise RuntimeError(respuesta.get("error") or "Falló la consulta WMI.")

    zonas = respuesta.get("zonas") or []
    if isinstance(zonas, dict):
        zonas = [zonas]
    if not isinstance(zonas, list):
        raise ValueError("La lista de zonas térmicas no es válida.")

    lecturas = []
    valores_invalidos = 0
    for indice, zona in enumerate(zonas, start=1):
        if not isinstance(zona, dict):
            valores_invalidos += 1
            continue

        try:
            temperatura_raw = zona["temperatura_raw"]
            if isinstance(temperatura_raw, bool):
                raise ValueError
            temperatura_raw = float(temperatura_raw)
            celsius = temperatura_raw / 10 - 273.15
            if not math.isfinite(celsius) or not -40 <= celsius <= 200:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            valores_invalidos += 1
            continue

        instancia = str(zona.get("instancia") or "").strip()
        lecturas.append(
            {
                "fuente": "ACPI/WMI",
                "tipo": "zona_termica_acpi",
                "nombre": instancia.rsplit("\\", 1)[-1] or f"zona {indice}",
                "instancia": instancia or None,
                "temperatura_raw": temperatura_raw,
                "unidad_raw": "decimas_kelvin",
                "temperatura_c": round(celsius, 2),
            }
        )

    if zonas and not lecturas:
        raise ValueError(
            f"WMI devolvió {valores_invalidos} temperatura(s) inválida(s)."
        )
    return lecturas


def _interpretar_resultado(salida, error_salida, codigo_salida, duracion):
    try:
        sensores = convertir_temperaturas(salida)
        if codigo_salida:
            raise RuntimeError(error_salida.strip() or "PowerShell terminó con error.")
        estado = "ok" if sensores else "sin_sensores"
        return _crear_muestra(estado, sensores, duracion=duracion)
    except (RuntimeError, ValueError) as error:
        detalle = str(error).strip()
        stderr = error_salida.strip()
        if stderr and stderr not in detalle:
            detalle = f"{detalle} Detalle de PowerShell: {stderr}"
        return _crear_muestra("error", error=detalle, duracion=duracion)


def proceso_recolector(cola_datos):
    """Consulta sensores en segundo plano y guarda muestras con diagnóstico."""
    lectura = None
    inicio_lectura = None
    lectura_vencida = False
    proxima_lectura = 0.0
    intervalo_lectura = max(0.1, float(INTERVALO_RECOLECCION))
    intervalo_reintento = max(intervalo_lectura, float(REINTENTO_SIN_LECTURA))

    try:
        while True:
            ahora = time.monotonic()
            if lectura is None and ahora >= proxima_lectura:
                try:
                    lectura = iniciar_lectura_temperaturas()
                except OSError as error:
                    cola_datos.append(_crear_muestra("error", error=str(error)))
                    proxima_lectura = ahora + intervalo_reintento
                else:
                    inicio_lectura, lectura_vencida = ahora, False

            if lectura is not None:
                codigo = lectura.poll()
                if codigo is None:
                    if (
                        not lectura_vencida
                        and ahora - inicio_lectura >= TIEMPO_MAXIMO_LECTURA
                    ):
                        lectura.kill()
                        lectura_vencida = True
                else:
                    try:
                        salida, error_salida = lectura.communicate()
                    except OSError as error:
                        salida, error_salida = "", str(error)

                    duracion = time.monotonic() - inicio_lectura
                    if lectura_vencida:
                        muestra = _crear_muestra(
                            "timeout",
                            error=f"La consulta excedió {TIEMPO_MAXIMO_LECTURA} s.",
                            duracion=duracion,
                        )
                    else:
                        muestra = _interpretar_resultado(
                            salida or "", error_salida or "", codigo, duracion
                        )

                    cola_datos.append(muestra)
                    proxima_lectura = time.monotonic() + (
                        intervalo_lectura
                        if muestra["estado"] == "ok"
                        else intervalo_reintento
                    )
                    lectura, inicio_lectura = None, None

            yield "LISTO"
    finally:
        if lectura is not None:
            try:
                if lectura.poll() is None:
                    lectura.kill()
                lectura.communicate()
            except OSError:
                pass
