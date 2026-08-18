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
  - `normalize_media.py`: prepara los archivos antes de publicar. Anade una
    pista de audio silenciosa a los videos que no tengan audio y avisa de
    formatos raros. Se ejecuta solo, no hay que llamarlo a mano.
  - `publish.py`: valida el post, crea los containers, espera el procesado,
    arma el carrusel y publica.
  - `published.json`: registro de lo ya publicado. Sirve para no publicar dos
    veces el mismo carrusel. Lo escribe el robot, no hace falta tocarlo.
  - Secrets del repo (Settings > Secrets and variables > Actions):
    `IG_ACCESS_TOKEN` (token de larga duracion, 60 dias) e `IG_USER_ID`.

## Como publicar un post nuevo (con ayuda de Claude)

1. Decirle a Claude "publica esto" senalando una carpeta con las imagenes.
2. Claude copia/sube esos archivos a `media/` en este repo.
3. Claude propone un caption (estilo meiko.anime); se revisa y aprueba.
4. Claude escribe `post-config.json` en la raiz del repo con el orden final
   de archivos (rutas dentro de `media/`) y el caption aprobado, y hace push.
5. Ese push dispara el workflow automaticamente. El robot (GitHub Actions)
   publica el carrusel sin que nadie tenga que ejecutar nada a mano.

## Formato de post-config.json

```json
{
  "caption": "texto del post",
  "media": [
    {"path": "media/archivo1.jpg", "type": "IMAGE"},
    {"path": "media/video.mp4", "type": "VIDEO"},
    {"path": "media/archivo2.jpg", "type": "IMAGE"}
  ]
}
```

## Que hace el robot al publicar

El workflow ejecuta estos pasos, y se para en cuanto algo no cuadra:

0. **Comprueba el token** contra la API antes de subir nada. Si el token esta
   caducado o bloqueado, el run falla en 2 segundos en vez de a mitad.
1. **Normaliza los medios**: si algun video no tiene pista de audio, le anade
   una en silencio y commitea el archivo corregido. Instagram rechaza los
   videos mudos, asi que esto ya no hay que hacerlo a mano. Tambien avisa si
   un video dura menos de 3s o mas de 60s, si la relacion de aspecto se sale
   del rango 0.80-1.91, o si las piezas no miden todas lo mismo.
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

Si hace falta volver a publicar un carrusel que ya consta en `published.json`:
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

- Primer post publicado manualmente (via script .ps1 local) el 15 ago 2026:
  carrusel "TOP animes verano 2026", 10 items.
- Infraestructura de GitHub Actions montada el mismo dia para publicaciones
  futuras sin pasos manuales.
- 18 ago 2026: post "TOP 7 animes sobre bucles temporales". Fallo dos veces
  (video sin audio, y publicacion lanzada antes de que el carrusel estuviera
  listo). A raiz de eso se anadio `normalize_media.py`, la espera real del
  carrusel, los reintentos, las validaciones previas y el registro
  anti-duplicados.
