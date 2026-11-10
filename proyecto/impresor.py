from datetime import datetime


def _hora_muestra(muestra):
    hora = muestra.get("capturada_en")
    return hora if hora is not None else datetime.now().astimezone()


def proceso_impresor(cola_datos):
    """Muestra el resultado más reciente sin atribuir ACPI directamente a CPU."""
    ultima_muestra_impresa = None
    anuncio_espera_impreso = False
    while True:
        if not cola_datos:
            if not anuncio_espera_impreso:
                print("\nEsperando la primera lectura de sensores.")
                anuncio_espera_impreso = True
            yield "BLOQUEAR"
            continue

        muestra = cola_datos[-1]
        if muestra is ultima_muestra_impresa:
            yield "BLOQUEAR"
            continue

        ultima_muestra_impresa = muestra
        hora = _hora_muestra(muestra)
        estado = muestra.get("estado", "error")

        if estado == "ok":
            print(
                f"\n[{hora:%H:%M:%S}] Zonas térmicas ACPI "
            )
            for sensor in muestra.get("sensores", []):
                print(
                    f"  {sensor.get('fuente', 'ACPI/WMI'):<12} "
                    f"{sensor.get('nombre', 'zona'):<20} "
                    f"{sensor.get('temperatura_c', float('nan')):>7.2f} C"
                )
                instancia = sensor.get("instancia")
                if instancia:
                    print(f"    Identificador WMI: {instancia}")
        elif estado == "sin_sensores":
            print(
                f"\n[{hora:%H:%M:%S}] Windows no expuso zonas térmicas ACPI. "
                "Esto no descarta otros sensores."
            )
        elif estado == "timeout":
            print(f"\n[{hora:%H:%M:%S}] Consulta de sensores cancelada por tiempo.")
        else:
            detalle = (muestra.get("error") or "Error sin detalle.").replace(
                "\r", " "
            ).replace("\n", " ")
            print(f"\n[{hora:%H:%M:%S}] Error al consultar sensores: {detalle}")

        duracion = muestra.get("duracion_s")
        if duracion is not None:
            print(f"  Duración de consulta: {duracion:.3f} s")
        yield "BLOQUEAR"
