"""
Prepara los archivos de media/ antes de publicarlos en Instagram.

Dos modos:

  python3 normalize_media.py --revisar
      Solo mira. No necesita ffmpeg: lee los propios archivos (cajas MP4,
      cabeceras JPEG/PNG) para saber si algun video esta mudo y si hay
      medidas raras. Deja en la salida del step si hace falta arreglar algo.

  python3 normalize_media.py
      Arregla: anade una pista de audio silenciosa a los videos mudos.
      Esto si necesita ffmpeg, pero el workflow solo llega aqui cuando la
      revision ha dicho que hay algo que arreglar.

Instagram rechaza los videos mudos en los carruseles (status ERROR al
procesarlos), de ahi la pista silenciosa.

Lo normal es que los videos lleguen ya con audio y que este script no toque
nada ni necesite instalar herramientas.
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


# --------------------------------------------------------------------------
# Lectura de los archivos sin depender de ffmpeg
# --------------------------------------------------------------------------

def _cajas(f, inicio, fin):
    """Devuelve (tipo, inicio_datos, fin_caja) de cada caja MP4 en [inicio, fin)."""
    pos = inicio
    while pos + 8 <= fin:
        f.seek(pos)
        cabecera = f.read(8)
        if len(cabecera) < 8:
            return
        tamano = int.from_bytes(cabecera[0:4], "big")
        tipo = cabecera[4:8]
        datos = pos + 8
        if tamano == 1:                      # tamano de 64 bits
            extra = f.read(8)
            if len(extra) < 8:
                return
            tamano = int.from_bytes(extra, "big")
            datos = pos + 16
        elif tamano == 0:                    # la caja llega hasta el final
            tamano = fin - pos
        if tamano < 8:
            return
        yield tipo, datos, min(pos + tamano, fin)
        pos += tamano


def _buscar(f, inicio, fin, camino, profundidad=0):
    """Busca una caja siguiendo un camino, p.ej. [b'moov', b'mvhd']."""
    if not camino or profundidad > 8:
        return None
    for tipo, datos, final in _cajas(f, inicio, fin):
        if tipo != camino[0]:
            continue
        if len(camino) == 1:
            return datos, final
        encontrado = _buscar(f, datos, final, camino[1:], profundidad + 1)
        if encontrado:
            return encontrado
    return None


def video_tiene_audio(ruta):
    """True si el MP4 lleva un 'trak' con manejador de sonido."""
    def buscar_soun(f, inicio, fin, profundidad=0):
        if profundidad > 6:
            return False
        for tipo, datos, final in _cajas(f, inicio, fin):
            if tipo == b"hdlr":
                f.seek(datos + 8)            # version+flags (4) + pre_defined (4)
                if f.read(4) == b"soun":
                    return True
            elif tipo in (b"moov", b"trak", b"mdia"):
                if buscar_soun(f, datos, final, profundidad + 1):
                    return True
        return False

    with open(ruta, "rb") as f:
        return buscar_soun(f, 0, os.path.getsize(ruta))


def video_duracion(ruta):
    """Duracion en segundos leida de la caja mvhd, o None."""
    with open(ruta, "rb") as f:
        sitio = _buscar(f, 0, os.path.getsize(ruta), [b"moov", b"mvhd"])
        if not sitio:
            return None
        datos, _ = sitio
        f.seek(datos)
        version = f.read(1)[0]
        if version == 1:
            f.seek(datos + 20)
            escala = int.from_bytes(f.read(4), "big")
            duracion = int.from_bytes(f.read(8), "big")
        else:
            f.seek(datos + 12)
            escala = int.from_bytes(f.read(4), "big")
            duracion = int.from_bytes(f.read(4), "big")
        return duracion / escala if escala else None


def video_dimensiones(ruta):
    """(ancho, alto) leidos de la caja tkhd, o None."""
    with open(ruta, "rb") as f:
        sitio = _buscar(f, 0, os.path.getsize(ruta), [b"moov", b"trak", b"tkhd"])
        if not sitio:
            return None
        datos, final = sitio
        f.seek(final - 8)
        crudo = f.read(8)
        if len(crudo) < 8:
            return None
        ancho = int.from_bytes(crudo[0:4], "big") / 65536.0
        alto = int.from_bytes(crudo[4:8], "big") / 65536.0
        if ancho <= 0 or alto <= 0:
            return None
        return int(round(ancho)), int(round(alto))


def imagen_dimensiones(ruta):
    """(ancho, alto) de un JPEG o PNG leyendo la cabecera, o None."""
    with open(ruta, "rb") as f:
        inicio = f.read(8)
        if inicio.startswith(b"\x89PNG"):
            f.seek(16)
            crudo = f.read(8)
            if len(crudo) < 8:
                return None
            return (int.from_bytes(crudo[0:4], "big"),
                    int.from_bytes(crudo[4:8], "big"))
        if not inicio.startswith(b"\xff\xd8"):
            return None
        f.seek(2)
        con_tamano = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
                      0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
        while True:
            byte = f.read(1)
            if not byte:
                return None
            if byte != b"\xff":
                continue
            marcador = f.read(1)
            while marcador == b"\xff":
                marcador = f.read(1)
            if not marcador:
                return None
            codigo = marcador[0]
            if codigo == 0x01 or 0xd0 <= codigo <= 0xd9:
                continue
            crudo = f.read(2)
            if len(crudo) < 2:
                return None
            longitud = int.from_bytes(crudo, "big")
            if codigo in con_tamano:
                cuerpo = f.read(5)
                if len(cuerpo) < 5:
                    return None
                return (int.from_bytes(cuerpo[3:5], "big"),
                        int.from_bytes(cuerpo[1:3], "big"))
            f.seek(longitud - 2, 1)


def dimensiones(ruta, tipo):
    return video_dimensiones(ruta) if tipo == "VIDEO" else imagen_dimensiones(ruta)


# --------------------------------------------------------------------------
# Arreglo (esto si necesita ffmpeg)
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------

def cargar_config():
    if not os.path.isfile(CONFIG):
        print(f"ERROR: no encuentro {CONFIG}")
        return None
    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)
    if not config.get("media"):
        print("ERROR: post-config.json no tiene medios")
        return None
    return config


def apuntar_salida(clave, valor):
    ruta = os.environ.get("GITHUB_OUTPUT")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"{clave}={valor}\n")


def apuntar_resumen(texto):
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(texto)


def revisar(config):
    """Mira los archivos sin tocar nada. No necesita ffmpeg."""
    mudos = []
    avisos = []
    formas = set()

    print("=== Revisando medios ===")
    for item in config["media"]:
        ruta = item.get("path", "")
        tipo = item.get("type")
        if not os.path.isfile(ruta):
            print(f"ERROR: no existe el archivo {ruta}")
            return None

        medida = dimensiones(ruta, tipo)
        if medida:
            formas.add(medida)
            aspecto = medida[0] / medida[1]
            if not (ASPECTO_MIN - 0.01 <= aspecto <= ASPECTO_MAX + 0.01):
                avisos.append(
                    f"{ruta}: relacion de aspecto {aspecto:.2f} fuera del rango "
                    f"admitido por Instagram (0.80 - 1.91)")
        else:
            avisos.append(f"{ruta}: no he podido leer las dimensiones")

        if tipo != "VIDEO":
            print(f"  {ruta}: imagen, nada que hacer")
            continue

        segundos = video_duracion(ruta)
        if segundos is None:
            avisos.append(f"{ruta}: no he podido leer la duracion")
        elif not (DURACION_MIN <= segundos <= DURACION_MAX):
            avisos.append(
                f"{ruta}: dura {segundos:.1f}s, Instagram admite entre "
                f"{DURACION_MIN:.0f}s y {DURACION_MAX:.0f}s en carrusel")

        if video_tiene_audio(ruta):
            print(f"  {ruta}: video con audio, nada que hacer")
        else:
            print(f"  {ruta}: video SIN audio -> hay que anadirle pista silenciosa")
            mudos.append(ruta)

    if len(formas) > 1:
        medidas = ", ".join(f"{a}x{b}" for a, b in sorted(formas))
        avisos.append(
            "las piezas no tienen todas el mismo tamano (" + medidas + "). "
            "Instagram recortara todo al formato de la primera")

    if avisos:
        print("=== Avisos ===")
        for aviso in avisos:
            print("  !", aviso)
        apuntar_resumen("### Avisos de formato\n"
                        + "".join(f"- {a}\n" for a in avisos))

    if mudos:
        print(f"=== Hay {len(mudos)} video(s) sin audio: " + ", ".join(mudos) + " ===")
    else:
        print("=== Todo en orden, no hace falta tocar ningun archivo ===")

    apuntar_salida("hay_que_arreglar", "true" if mudos else "false")
    return mudos


def arreglar(mudos):
    """Anade la pista silenciosa. Esto si necesita ffmpeg."""
    if not mudos:
        print("Nada que arreglar.")
        return 0

    if not shutil.which("ffmpeg"):
        print("ERROR: hacen falta arreglos pero no hay ffmpeg disponible.")
        print("Videos sin audio:", ", ".join(mudos))
        print("Instagram rechaza los videos mudos en un carrusel.")
        return 1

    corregidos = []
    for ruta in mudos:
        print(f"  {ruta}: anadiendo pista de audio silenciosa")
        anadir_audio_silencioso(ruta)
        if not video_tiene_audio(ruta):
            print(f"ERROR: no he conseguido anadir audio a {ruta}")
            return 1
        corregidos.append(ruta)
        print(f"  {ruta}: arreglado ({os.path.getsize(ruta)} bytes)")

    print(f"=== Corregidos {len(corregidos)} video(s) ===")
    apuntar_resumen("### Medios normalizados\n"
                    + "".join(f"- Pista de audio silenciosa anadida a `{r}`\n"
                              for r in corregidos))
    return 0


def main():
    config = cargar_config()
    if config is None:
        return 1

    mudos = revisar(config)
    if mudos is None:
        return 1

    if "--revisar" in sys.argv:
        return 0

    return arreglar(mudos)


if __name__ == "__main__":
    sys.exit(main())
