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
  - `publish.py`: script que crea los containers, espera el procesado del
    video, arma el carrusel y publica.
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

## Mantenimiento

- **Token de Instagram** (`IG_ACCESS_TOKEN`): caduca ~60 dias despues de
  generado (mediados de octubre 2026). Se renueva con una llamada GET a
  graph.instagram.com/refresh_access_token, o repitiendo el flujo OAuth.
- **Token de GitHub** usado para el hosting: caduca el 13 nov 2026
  (scopes: public_repo, workflow). Renovar en github.com/settings/tokens.

## Historial

- Primer post publicado manualmente (via script .ps1 local) el 15 ago 2026:
  carrusel "TOP animes verano 2026", 10 items.
- Infraestructura de GitHub Actions montada el mismo dia para publicaciones
  futuras sin pasos manuales.
