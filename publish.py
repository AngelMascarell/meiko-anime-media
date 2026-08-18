import json, os, sys, time, urllib.request, urllib.parse, urllib.error

TOKEN = os.environ["IG_TOKEN"]
IG_ID = os.environ["IG_USER_ID"]
REPO = os.environ.get("GITHUB_REPOSITORY", "AngelMascarell/meiko-anime-media")
BASE_URL = f"https://raw.githubusercontent.com/{REPO}/main/"
API = "https://graph.instagram.com/v21.0/"

MAX_INTENTOS = 6          # reintentos ante errores temporales de la API
ESPERA_BASE = 15          # segundos, va subiendo en cada reintento
TIMEOUT_PROCESADO = 600   # maximo esperando a que un contenedor este FINISHED


def _peticion(url, method):
    data = b"" if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def _es_temporal(payload, status):
    """Meta devuelve errores pasajeros que se resuelven solos reintentando."""
    err = payload.get("error", {}) if isinstance(payload, dict) else {}
    if err.get("is_transient"):
        return True
    # 2207027 = "The media is not ready for publishing, please wait for a moment"
    if err.get("error_subcode") == 2207027:
        return True
    if err.get("code") in (1, 2):
        return True
    return status >= 500


def api(path, params, method="POST", etiqueta=""):
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
            print("ERROR HTTP", e.code, cuerpo)
            sys.exit(1)
        except urllib.error.URLError as e:
            if intento < MAX_INTENTOS:
                espera = ESPERA_BASE * intento
                print(f"   aviso: {nombre} error de red ({e.reason}). "
                      f"Reintento {intento}/{MAX_INTENTOS - 1} en {espera}s")
                time.sleep(espera)
                continue
            print("ERROR de red:", e.reason)
            sys.exit(1)


def esperar_finished(container_id, etiqueta):
    """Sondea el contenedor hasta que Instagram lo marca como FINISHED."""
    limite = time.time() + TIMEOUT_PROCESADO
    while True:
        estado = api(container_id,
                     {"fields": "status_code", "access_token": TOKEN},
                     method="GET",
                     etiqueta=f"estado {etiqueta}")
        code = estado.get("status_code")
        print(f"   {etiqueta} ({container_id}) -> {code}")
        if code == "FINISHED":
            return
        if code == "ERROR":
            print("ERROR procesando", etiqueta, container_id)
            sys.exit(1)
        if time.time() > limite:
            print("TIMEOUT esperando", etiqueta, container_id)
            sys.exit(1)
        time.sleep(5)


with open("post-config.json", encoding="utf-8") as f:
    config = json.load(f)

print("=== Paso 1: creando contenedores ===")
container_ids = []
for item in config["media"]:
    file_url = BASE_URL + urllib.parse.quote(item["path"])
    params = {"access_token": TOKEN, "is_carousel_item": "true"}
    if item["type"] == "VIDEO":
        params["media_type"] = "VIDEO"
        params["video_url"] = file_url
    else:
        params["image_url"] = file_url
    resp = api(f"{IG_ID}/media", params, etiqueta=item["path"])
    print("OK", item["path"], "->", resp.get("id"))
    container_ids.append((resp["id"], item["path"]))
    time.sleep(2)

print("=== Paso 2: esperando procesamiento de cada media ===")
for cid, nombre in container_ids:
    esperar_finished(cid, nombre)

print("=== Paso 3: creando carrusel ===")
children = ",".join(cid for cid, _ in container_ids)
carousel = api(f"{IG_ID}/media", {
    "access_token": TOKEN,
    "media_type": "CAROUSEL",
    "children": children,
    "caption": config["caption"],
}, etiqueta="carrusel")
carousel_id = carousel["id"]
print("Carousel container:", carousel_id)

print("=== Paso 4: esperando a que el carrusel este listo ===")
esperar_finished(carousel_id, "carrusel")

print("=== Paso 5: publicando ===")
publish = api(f"{IG_ID}/media_publish", {
    "access_token": TOKEN,
    "creation_id": carousel_id,
}, etiqueta="media_publish")
print("PUBLICADO! Media ID:", publish.get("id"))
