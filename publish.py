"""
Publica el carrusel definido en post-config.json en Instagram.

Orden de trabajo:
  0. Comprueba que el token funciona (falla rapido, antes de subir nada).
  1. Valida post-config.json contra los limites de Instagram.
  2. Comprueba que ya se ha publicado este mismo post (evita duplicados).
  3. Verifica que GitHub sirve cada archivo por su URL publica.
  4. Crea un contenedor por cada media y espera a que este FINISHED.
  5. Crea el carrusel, espera a que este listo y lo publica.
  6. Deja constancia en published.json (el workflow lo commitea).

Variables de entorno:
  IG_TOKEN        obligatorio, token de acceso de Instagram
  IG_USER_ID      obligatorio, id de la cuenta
  FORCE_PUBLISH   opcional, "1" para republicar aunque ya conste publicado
"""

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ["IG_TOKEN"]
IG_ID = os.environ["IG_USER_ID"]
REPO = os.environ.get("GITHUB_REPOSITORY", "AngelMascarell/meiko-anime-media")
RAMA = os.environ.get("GITHUB_REF_NAME", "main")
BASE_URL = f"https://raw.githubusercontent.com/{REPO}/main/"
API = "https://graph.instagram.com/v21.0/"

CONFIG = "post-config.json"
REGISTRO = "published.json"
REGISTRO_URL = BASE_URL + REGISTRO

MAX_INTENTOS = 6            # reintentos ante errores temporales de la API
ESPERA_BASE = 15            # segundos, sube en cada reintento
TIMEOUT_PROCESADO = 900     # maximo esperando a que un contenedor este listo
INTENTOS_CDN = 18           # ~3 min esperando a que GitHub sirva un archivo

# Limites de Instagram
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MIN_MEDIA = 2
MAX_MEDIA = 10


# --------------------------------------------------------------------------
# Llamadas a la API con reintentos
# --------------------------------------------------------------------------

def _peticion(url, method):
    data = b"" if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _es_temporal(payload, status):
    """Meta devuelve errores pasajeros que se resuelven solos reintentando."""
    err = payload.get("error", {}) if isinstance(payload, dict) else {}
    if err.get("is_transient"):
        return True
    # 2207027 = "The media is not ready for publishing, please wait a moment"
    if err.get("error_subcode") == 2207027:
        return True
    if err.get("code") in (1, 2):
        return True
    return status >= 500


def api(path, params, method="POST", etiqueta="", critico=True):
    """Llama a la Graph API. Devuelve None si falla y critico=False."""
    url = API + path + "?" + urllib.parse.urlencode(params)
    nombre = etiqueta or path
    for intento in range(1, MAX_INTENTOS + 1):
        try:
            return _peticion(url, method)
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode()
            try:
                payload = json.loads(cuerpo)
            except ValueError:
                payload = {}
            if _es_temporal(payload, e.code) and intento < MAX_INTENTOS:
                espera = ESPERA_BASE * intento
                print(f"   aviso: {nombre} fallo temporal (HTTP {e.code}). "
                      f"Reintento {intento}/{MAX_INTENTOS - 1} en {espera}s")
                print("   detalle:", cuerpo)
                time.sleep(espera)
                continue
            if not critico:
                return None
            error(f"la API ha devuelto HTTP {e.code} en {nombre}", cuerpo)
        except (urllib.error.URLError, TimeoutError) as e:
            if intento < MAX_INTENTOS:
                espera = ESPERA_BASE * intento
                print(f"   aviso: {nombre} error de red ({e}). "
                      f"Reintento {intento}/{MAX_INTENTOS - 1} en {espera}s")
                time.sleep(espera)
                continue
            if not critico:
                return None
            error(f"error de red hablando con la API en {nombre}", str(e))


def error(mensaje, detalle=""):
    print()
    print("ERROR:", mensaje)
    if detalle:
        print("Detalle:", detalle)
    resumen(f"### Publicacion fallida\n\n{mensaje}\n\n```\n{detalle}\n```\n")
    sys.exit(1)


def resumen(texto):
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(texto)


# --------------------------------------------------------------------------
# Pasos
# --------------------------------------------------------------------------

def comprobar_token():
    cuenta = api("me", {"fields": "id,username", "access_token": TOKEN},
                 method="GET", etiqueta="comprobacion de token")
    usuario = cuenta.get("username", "?")
    print(f"Token valido. Publicando como @{usuario} (id {cuenta.get('id')})")
    return usuario


def validar(config):
    errores = []
    caption = config.get("caption", "")
    media = config.get("media", [])

    if not isinstance(caption, str) or not caption.strip():
        errores.append("el caption esta vacio")
    if len(caption) > MAX_CAPTION:
        errores.append(f"el caption tiene {len(caption)} caracteres "
                       f"(el maximo son {MAX_CAPTION})")

    hashtags = re.findall(r"#\w+", caption)
    if len(hashtags) > MAX_HASHTAGS:
        errores.append(f"hay {len(hashtags)} hashtags "
                       f"(el maximo son {MAX_HASHTAGS})")

    if not isinstance(media, list) or not (MIN_MEDIA <= len(media) <= MAX_MEDIA):
        errores.append(f"un carrusel necesita entre {MIN_MEDIA} y {MAX_MEDIA} "
                       f"elementos (hay {len(media)})")

    vistos = set()
    for i, item in enumerate(media, 1):
        ruta = item.get("path")
        tipo = item.get("type")
        if not ruta:
            errores.append(f"el elemento {i} no tiene 'path'")
            continue
        if tipo not in ("IMAGE", "VIDEO"):
            errores.append(f"{ruta}: 'type' debe ser IMAGE o VIDEO (es {tipo!r})")
        if not os.path.isfile(ruta):
            errores.append(f"{ruta}: el archivo no existe en el repo")
        if ruta in vistos:
            errores.append(f"{ruta}: esta repetido en el carrusel")
        vistos.add(ruta)
        extension = os.path.splitext(ruta)[1].lower()
        if tipo == "IMAGE" and extension not in (".jpg", ".jpeg", ".png"):
            errores.append(f"{ruta}: Instagram solo acepta jpg o png en imagenes")
        if tipo == "VIDEO" and extension not in (".mp4", ".mov"):
            errores.append(f"{ruta}: Instagram solo acepta mp4 o mov en video")

    if errores:
        print("La configuracion del post tiene problemas:")
        for e in errores:
            print("  -", e)
        error(f"{len(errores)} problema(s) en {CONFIG}",
              "\n".join(errores))

    print(f"Configuracion valida: {len(media)} piezas, "
          f"{len(caption)} caracteres de caption, {len(hashtags)} hashtags")


def huella(config):
    """Identifica el post por su contenido, no por el commit."""
    canonico = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def cargar_registro():
    """Lee published.json de la rama principal, no del checkout local.

    Asi el control de duplicados sigue funcionando aunque se relance un run
    antiguo de Actions (que hace checkout de un commit anterior).
    """
    try:
        url = REGISTRO_URL + "?cb=" + str(int(time.time()))
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except Exception:
        pass
    if os.path.isfile(REGISTRO):
        try:
            with open(REGISTRO, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            pass
    return {"posts": []}


def guardar_registro(registro, entrada):
    registro.setdefault("posts", []).append(entrada)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
        f.write("\n")


def verificar_disponible(url, tam_local, etiqueta):
    """Espera a que GitHub sirva el archivo actual por su URL publica."""
    for intento in range(1, INTENTOS_CDN + 1):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as resp:
                tam_remoto = int(resp.headers.get("Content-Length", -1))
            if tam_remoto == tam_local:
                return
            print(f"   {etiqueta}: GitHub sirve {tam_remoto} bytes y el repo "
                  f"tiene {tam_local}. Esperando al CDN "
                  f"({intento}/{INTENTOS_CDN})")
        except urllib.error.HTTPError as e:
            print(f"   {etiqueta}: HTTP {e.code} al pedir el archivo. "
                  f"Esperando al CDN ({intento}/{INTENTOS_CDN})")
        except Exception as e:
            print(f"   {etiqueta}: {e}. Reintento ({intento}/{INTENTOS_CDN})")
        time.sleep(10)
    error(f"{etiqueta} no esta disponible publicamente en {url}",
          "Instagram necesita descargar el archivo desde esa URL. "
          "Comprueba que el archivo esta commiteado en la rama main.")


def esperar_finished(container_id, etiqueta):
    limite = time.time() + TIMEOUT_PROCESADO
    ultimo = None
    while True:
        estado = api(container_id,
                     {"fields": "status_code,status", "access_token": TOKEN},
                     method="GET", etiqueta=f"estado de {etiqueta}")
        code = estado.get("status_code")
        if code != ultimo:
            print(f"   {etiqueta} ({container_id}) -> {code}")
            ultimo = code
        if code == "FINISHED":
            return
        if code == "ERROR":
            error(f"Instagram no ha podido procesar {etiqueta}",
                  estado.get("status", "sin detalle"))
        if time.time() > limite:
            error(f"se ha agotado el tiempo esperando a {etiqueta}",
                  f"ultimo estado conocido: {code}")
        time.sleep(5)


# --------------------------------------------------------------------------

def main():
    if not os.path.isfile(CONFIG):
        error(f"no encuentro {CONFIG}")
    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)

    print("=== Paso 0: comprobando el token ===")
    usuario = comprobar_token()

    print("=== Paso 1: validando la configuracion del post ===")
    validar(config)

    print("=== Paso 2: comprobando que no este ya publicado ===")
    hash_post = huella(config)
    registro = cargar_registro()
    ya = next((p for p in registro.get("posts", [])
               if p.get("hash") == hash_post), None)
    if ya and os.environ.get("FORCE_PUBLISH") != "1":
        print(f"Este post ya se publico el {ya.get('published_at')} "
              f"(media id {ya.get('media_id')}).")
        print("No hago nada. Si quieres repetirlo, lanza el workflow con "
              "FORCE_PUBLISH=1 o cambia post-config.json.")
        resumen(f"### Nada que publicar\n\nEste carrusel ya se publico el "
                f"{ya.get('published_at')} (media id `{ya.get('media_id')}`).\n")
        return 0
    print("Post nuevo, seguimos.")

    print("=== Paso 3: comprobando que GitHub sirve los archivos ===")
    for item in config["media"]:
        url = BASE_URL + urllib.parse.quote(item["path"])
        verificar_disponible(url, os.path.getsize(item["path"]), item["path"])
    print(f"Los {len(config['media'])} archivos estan accesibles")

    print("=== Paso 4: creando contenedores ===")
    contenedores = []
    for item in config["media"]:
        url = BASE_URL + urllib.parse.quote(item["path"])
        params = {"access_token": TOKEN, "is_carousel_item": "true"}
        if item["type"] == "VIDEO":
            params["media_type"] = "VIDEO"
            params["video_url"] = url
        else:
            params["image_url"] = url
        resp = api(f"{IG_ID}/media", params, etiqueta=item["path"])
        print("  OK", item["path"], "->", resp.get("id"))
        contenedores.append((resp["id"], item["path"]))
        time.sleep(2)

    print("=== Paso 5: esperando a que Instagram procese cada pieza ===")
    for cid, nombre in contenedores:
        esperar_finished(cid, nombre)

    print("=== Paso 6: creando el carrusel ===")
    carrusel = api(f"{IG_ID}/media", {
        "access_token": TOKEN,
        "media_type": "CAROUSEL",
        "children": ",".join(cid for cid, _ in contenedores),
        "caption": config["caption"],
    }, etiqueta="carrusel")
    carrusel_id = carrusel["id"]
    print("  Contenedor del carrusel:", carrusel_id)
    esperar_finished(carrusel_id, "carrusel")

    print("=== Paso 7: publicando ===")
    publicado = api(f"{IG_ID}/media_publish", {
        "access_token": TOKEN,
        "creation_id": carrusel_id,
    }, etiqueta="media_publish")
    media_id = publicado.get("id")
    print("  PUBLICADO! Media ID:", media_id)

    # El permalink es un extra: si falla no tumbamos el run, ya esta publicado.
    detalle = api(media_id, {"fields": "permalink", "access_token": TOKEN},
                  method="GET", etiqueta="permalink", critico=False) or {}
    enlace = detalle.get("permalink", "")
    if enlace:
        print("  Enlace:", enlace)

    print("=== Paso 8: guardando el registro ===")
    guardar_registro(registro, {
        "hash": hash_post,
        "media_id": media_id,
        "permalink": enlace,
        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "caption_preview": config["caption"].split("\n", 1)[0][:120],
        "media": [i["path"] for i in config["media"]],
    })
    print(f"  Anotado en {REGISTRO}")

    resumen(
        f"### Publicado en Instagram\n\n"
        f"- Cuenta: **@{usuario}**\n"
        f"- Media ID: `{media_id}`\n"
        + (f"- Enlace: {enlace}\n" if enlace else "")
        + f"- Piezas: {len(config['media'])}\n"
        f"- Caption: {config['caption'].splitlines()[0][:120]}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
