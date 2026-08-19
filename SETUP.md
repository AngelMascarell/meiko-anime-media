# Automatizacion de publicacion en Instagram - @meiko.anime

Este repo aloja las imagenes/videos publicos que necesita la API de Instagram
para publicar carruseles automaticamente en @meiko.anime, via GitHub Actions.

## Piezas del sistema

- **App de Meta**: "auto posting" (App ID: 1572367421052475), producto
  "Instagram API with Instagram Login". Instagram App ID: 1584352013129560.
- **Cuenta de Instagram**: @meiko.anime, IG User ID: 17841431422227912.
- **Repo de GitHub**: AngelMascarell/meiko-anime-media (este repo).
  - Carpeta `media/`: imagenes y videos ya subidos, servidos via
    raw.githubusercontent.com para que Instagram los pueda leer.
  - `.github/workflows/publish-instagram.yml`: workflow que se dispara al
    hacer push de `post-config.json`, o manualmente desde la pestana Actions
    (boton "Run workflow").
  - `normalize_media.py`: revisa los archivos y, si hace falta, arregla los
    videos mudos. Ver "El paso de los videos mudos" mas abajo.
  - `publish.py`: valida el post, crea los containers, espera el procesado,
    arma el carrusel y publica.
  - `published.json`: registro de lo ya publicado. Sirve para no publicar dos
    veces el mismo carrusel. Lo escribe el robot, no hace falta tocarlo.
  - Secrets del repo (Settings > Secrets and variables > Actions):
    `IG_ACCESS_TOKEN` (token de larga duracion, 60 dias) e `IG_USER_ID`.

---

## Procedimiento para publicar un post nuevo

Esta es la receta completa. Si se sigue tal cual, publicar un post son unos
3 minutos y no hay que tocar nada del sistema.

### 1. Recibir la carpeta

Angel conecta o sube una carpeta con las piezas del carrusel, normalmente 10,
numeradas del 1 al 10:

- `1.jpg` portada
- `2.jpg` a `8.jpg` los 7 animes
- `9.mp4` el video "¡NAKAMA!" (pregunta a la audiencia)
- `10.jpg` el cierre ("guarda el post")

### 2. Arreglar los videos ANTES de subirlos  ← el paso que mas se olvida

Instagram **rechaza los videos sin pista de audio** en un carrusel. El video
`9.mp4` que Angel exporta suele venir mudo.

Comprobarlo y arreglarlo antes de subir nada:

```bash
# ¿tiene audio?
ffprobe -v error -select_streams a -show_entries stream=codec_name \
  -of csv=p=0 9.mp4          # si no imprime nada, esta mudo

# arreglarlo (misma receta que usa normalize_media.py)
ffmpeg -y -loglevel error -i 9.mp4 \
  -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
  -shortest -c:v copy -c:a aac -b:a 128k -movflags +faststart \
  9-con-audio.mp4
```

Se sube el arreglado. Asi el workflow no tiene que instalar ninguna
herramienta y publica directo.

### 3. Renombrar con el prefijo del tema

En `media/` conviven los archivos de todos los posts, asi que **nunca** se
suben como `1.jpg`, `2.jpg`... (pisarian los de un post anterior). Se usa un
prefijo del tema:

```
fantasia-1.jpg    juegosmesa-1.jpg    bucles-1.jpg
fantasia-2.jpg    juegosmesa-2.jpg    bucles-2.jpg
...               ...                 ...
fantasia-9.mp4    juegosmesa-9.mp4    bucles-9.mp4
fantasia-10.jpg   juegosmesa-10.jpg   bucles-10.jpg
```

### 4. Subir los archivos a `media/`

Subir los 10 y **esperar a que el commit termine** antes de seguir. Si se
navega antes de tiempo, el commit se queda a medias y no sube nada.

### 5. Proponer el caption y esperar el visto bueno

Estilo @meiko.anime: tono cercano y con gracia, una coletilla corta al lado de
cada anime, sin sentimentalismos ni frases de folleto. Termina invitando a
comentar y a guardar el post, y cierra con "¡NAKAMA!".

No se escribe `post-config.json` hasta que Angel apruebe el caption: escribirlo
dispara la publicacion.

### 6. Escribir `post-config.json`

```json
{
  "caption": "texto aprobado",
  "media": [
    {"path": "media/juegosmesa-1.jpg", "type": "IMAGE"},
    {"path": "media/juegosmesa-9.mp4", "type": "VIDEO"}
  ]
}
```

El push de este archivo dispara el workflow. Tambien se puede lanzar a mano
desde Actions > Publish Instagram Carousel > "Run workflow".

### 7. Vigilar el run

Un run normal dura entre 1 y 3 minutos, casi todo esperando a que Instagram
procese el video. Al terminar, el resumen del run trae el media id y el
enlace al post.

---

## El paso de los videos mudos

Este es el punto que ha dado problemas y conviene entenderlo.

Instagram rechaza los videos sin audio en un carrusel, asi que hay que
anadirles una pista silenciosa. Eso lo hace `ffmpeg`, y **ffmpeg no viene
instalado en los runners de GitHub**.

Durante un tiempo el workflow instalaba ffmpeg con `apt-get` en *cada*
publicacion. Eso metia una dependencia de red en el camino critico de todos
los posts, y el 19 de agosto de 2026 `apt-get` se quedo esperando el lock de
`dpkg` y bloqueo dos runs seguidos (11 y 8 minutos sin una sola linea de log).

Ahora funciona asi:

1. **`normalize_media.py --revisar`** mira los archivos en Python puro: lee las
   cajas del MP4 para saber si hay pista de audio, y las cabeceras JPEG/PNG y
   MP4 para las medidas y la duracion. No necesita ffmpeg ni instalar nada, y
   tarda un segundo. Deja en la salida del step `hay_que_arreglar=true|false`.
2. Los pasos de **instalar ffmpeg**, **normalizar** y **guardar los medios
   corregidos** solo se ejecutan si esa revision ha dicho `true`.
3. Si los videos llegan ya con audio (lo normal, siguiendo el paso 2 del
   procedimiento), esos tres pasos se saltan enteros y el run va directo a
   publicar.

Es decir: `apt-get` ya no esta en el camino de un post normal. Y si algun dia
hiciera falta, esta acotado con `timeout` para que no pueda colgarse.

---

## Que hace el robot al publicar

El workflow se para en cuanto algo no cuadra:

0. **Comprueba el token** contra la API antes de subir nada. Si esta caducado
   o bloqueado, el run falla en 2 segundos en vez de a mitad.
1. **Revisa los medios** (Python puro, sin instalar nada).
2. **Valida `post-config.json`**: entre 2 y 10 piezas, caption de 2200
   caracteres como maximo, 30 hashtags como maximo, sin archivos repetidos,
   sin rutas que no existan y con extensiones que Instagram acepte.
3. **Comprueba duplicados**: si ese mismo carrusel (mismo caption y mismos
   archivos) ya consta en `published.json`, no publica nada y termina en
   verde. Esto evita duplicar el post al relanzar un run.
4. **Espera al CDN**: verifica que raw.githubusercontent.com ya sirve la
   version correcta de cada archivo antes de pasarle las URLs a Instagram.
5. **Publica** y espera de verdad a que cada pieza y el carrusel esten
   `FINISHED`, en vez de dormir unos segundos a ciegas.
6. **Anota el resultado** en `published.json` (media id, permalink y fecha) y
   escribe un resumen con el enlace al post en la pagina del run de Actions.

Los errores temporales de Meta (HTTP 500, `is_transient`, "media not ready")
se reintentan solos hasta 5 veces con esperas crecientes.

## Republicar un post a proposito

Actions > Publish Instagram Carousel > "Run workflow" > marcar la casilla
**"Publicar aunque este post ya conste como publicado"**.

## Mantenimiento

- **Token de Instagram** (`IG_ACCESS_TOKEN`): caduca ~60 dias despues de
  generado (mediados de octubre 2026). Se renueva con una llamada GET a
  graph.instagram.com/refresh_access_token, o repitiendo el flujo OAuth.
  Si el token falla, el run lo dice en el paso 0 con el error exacto.
- **Token de GitHub** usado para el hosting: caduca el 13 nov 2026
  (scopes: public_repo, workflow). Renovar en github.com/settings/tokens.

## Historial

- **15 ago 2026**: primer post publicado a mano (script .ps1 local): carrusel
  "TOP animes verano 2026", 10 items. Ese mismo dia se monta el workflow.
- **17 ago 2026**: "TOP 7 animes de fantasia". Fallo la primera vez con
  "API access blocked" (permiso de la app de Meta); se arreglo por el lado de
  Meta y se relanzo.
- **18 ago 2026**: "TOP 7 animes sobre bucles temporales". Fallo dos veces
  (video sin audio, y publicacion lanzada antes de que el carrusel estuviera
  listo). A raiz de eso se anadio `normalize_media.py`, la espera real del
  carrusel, los reintentos, las validaciones previas y el registro
  anti-duplicados.
- **19 ago 2026**: "TOP 7 animes sobre juegos de mesa". Dos runs bloqueados
  porque `apt-get` no podia instalar ffmpeg. Se rehizo la revision de medios
  en Python puro y se dejo la instalacion de ffmpeg como paso condicional,
  para sacar `apt-get` del camino critico. Se documento el procedimiento de
  arreglar los videos antes de subirlos.
