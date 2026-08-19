"""
Prepara los archivos de media/ antes de publicarlos en Instagram.

Ahora mismo hace dos cosas:
  1. Anade una pista de audio silenciosa a los videos que no tengan audio.
     Instagram rechaza los videos mudos en los carruseles (status ERROR al
     procesarlos), asi que esto se arregla solo sin tocar el video original.
  2. Avisa (sin bloquear) de cosas raras: duracion fuera de rango, relacion
     de aspecto no admitida o medidas distintas entre las piezas del carrusel.

No publica nada. El workflow lo ejecuta antes de publish.py y commitea los
archivos que hayan cambiado.
"""

import json
import os
import shutil
import subprocess
import sys

CONFIG = "post-config.json"

# Limites de Instagram para video en carrusel
DURACION_MIN = 3.0
DURACION_MAX = 60.0
ASPECTO_MIN = 4 / 5      # 0.80 vertical
ASPECTO_MAX = 1.91       # horizontal


def ffprobe(ruta, args):
    salida = subprocess.run(
        ["ffprobe", "-v", "error"] + args + [ruta],
        capture_output=True, text=True, check=True)
    return salida.stdout.strip()


def tiene_audio(ruta):
    salida = ffprobe(ruta, ["-select_streams", "a",
                            "-show_entries", "stream=codec_type",
                            "-of", "csv=p=0"])
    return "audio" in salida


def dimensiones(ruta):
    salida = ffprobe(ruta, ["-select_streams", "v:0",
                            "-show_entries", "stream=width,height",
                            "-of", "csv=p=0:s=x"])
    ancho, alto = salida.split("x")[:2]
    return int(ancho), int(alto)


def duracion(ruta):
    salida = ffprobe(ruta, ["-show_entries", "format=duration",
                            "-of", "csv=p=0"])
    return float(salida)


def anadir_audio_silencioso(ruta):
    """Copia el video tal cual y le pega una pista AAC en silencio."""
    temporal = ruta + ".tmp.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", ruta,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-shortest",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        temporal,
    ], check=True)
    os.replace(temporal, ruta)


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("AVISO: ffmpeg no esta disponible en este runner, me salto la "
              "normalizacion. Los videos deben llevar ya su pista de audio.")
        return 0

    if not os.path.isfile(CONFIG):
        print(f"ERROR: no encuentro {CONFIG}")
        return 1

    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)

    media = config.get("media", [])
    if not media:
        print("ERROR: post-config.json no tiene medios")
        return 1

    corregidos = []
    avisos = []
    formas = set()

    print("=== Revisando medios ===")
    for item in media:
        ruta = item.get("path", "")
        if not os.path.isfile(ruta):
            print(f"ERROR: no existe el archivo {ruta}")
            return 1

        try:
            ancho, alto = dimensiones(ruta)
            formas.add((ancho, alto))
            aspecto = ancho / alto
            if not (ASPECTO_MIN - 0.01 <= aspecto <= ASPECTO_MAX + 0.01):
                avisos.append(
                    f"{ruta}: relacion de aspecto {aspecto:.2f} fuera del rango "
                    f"admitido por Instagram (0.80 - 1.91)")
        except Exception as e:
            avisos.append(f"{ruta}: no he podido leer las dimensiones ({e})")

        if item.get("type") != "VIDEO":
            print(f"  {ruta}: imagen, nada que hacer")
            continue

        try:
            segundos = duracion(ruta)
            if not (DURACION_MIN <= segundos <= DURACION_MAX):
                avisos.append(
                    f"{ruta}: dura {segundos:.1f}s, Instagram admite entre "
                    f"{DURACION_MIN:.0f}s y {DURACION_MAX:.0f}s en carrusel")
        except Exception as e:
            avisos.append(f"{ruta}: no he podido leer la duracion ({e})")

        if tiene_audio(ruta):
            print(f"  {ruta}: video con audio, nada que hacer")
        else:
            print(f"  {ruta}: video SIN audio -> anadiendo pista silenciosa")
            anadir_audio_silencioso(ruta)
            if not tiene_audio(ruta):
                print(f"ERROR: no he conseguido anadir audio a {ruta}")
                return 1
            corregidos.append(ruta)
            print(f"  {ruta}: arreglado ({os.path.getsize(ruta)} bytes)")

    if len(formas) > 1:
        medidas = ", ".join(f"{a}x{b}" for a, b in sorted(formas))
        avisos.append(
            "las piezas no tienen todas el mismo tamano (" + medidas + "). "
            "Instagram recortara todo al formato de la primera")

    if avisos:
        print("=== Avisos ===")
        for aviso in avisos:
            print("  !", aviso)

    if corregidos:
        print(f"=== Corregidos {len(corregidos)} video(s): "
              + ", ".join(corregidos) + " ===")
    else:
        print("=== Todo en orden, ningun archivo modificado ===")

    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            if corregidos:
                f.write("### Medios normalizados\n")
                for ruta in corregidos:
                    f.write(f"- Pista de audio silenciosa anadida a `{ruta}`\n")
            if avisos:
                f.write("### Avisos de formato\n")
                for aviso in avisos:
                    f.write(f"- {aviso}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
