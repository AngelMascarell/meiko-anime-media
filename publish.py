import json, os, sys, time, urllib.request, urllib.parse, urllib.error

TOKEN = os.environ["IG_TOKEN"]
IG_ID = os.environ["IG_USER_ID"]
REPO = os.environ.get("GITHUB_REPOSITORY", "AngelMascarell/meiko-anime-media")
BASE_URL = f"https://raw.githubusercontent.com/{REPO}/main/"
API = "https://graph.instagram.com/v21.0/"


def call(path, params):
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print("ERROR HTTP", e.code, e.read().decode())
        sys.exit(1)


def get(path, params):
    url = API + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print("ERROR HTTP", e.code, e.read().decode())
        sys.exit(1)


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
    resp = call(f"{IG_ID}/media", params)
    print("OK", item["path"], "->", resp.get("id"))
    container_ids.append(resp["id"])
    time.sleep(2)

print("=== Paso 2: esperando procesamiento ===")
for cid in container_ids:
    while True:
        status = get(cid, {"fields": "status_code", "access_token": TOKEN})
        code = status.get("status_code")
        print(cid, "->", code)
        if code == "FINISHED":
            break
        if code == "ERROR":
            print("ERROR procesando", cid)
            sys.exit(1)
        time.sleep(5)

print("=== Paso 3: creando carrusel ===")
children = ",".join(container_ids)
carousel = call(f"{IG_ID}/media", {
    "access_token": TOKEN,
    "media_type": "CAROUSEL",
    "children": children,
    "caption": config["caption"],
})
print("Carousel container:", carousel.get("id"))

time.sleep(5)

print("=== Paso 4: publicando ===")
publish = call(f"{IG_ID}/media_publish", {
    "access_token": TOKEN,
    "creation_id": carousel["id"],
})
print("PUBLICADO! Media ID:", publish.get("id"))
