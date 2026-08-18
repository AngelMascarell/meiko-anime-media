# meiko-anime-media

Publicacion automatica de carruseles en Instagram (@meiko.anime) desde GitHub.

Este repo hace dos cosas: aloja los archivos del post (Instagram necesita
descargarlos desde una URL publica) y ejecuta el robot que los publica.

## Como se publica un post

1. Subir las piezas del carrusel a `media/`.
2. Escribir `post-config.json` en la raiz con el caption y el orden final.
3. Hacer push. Eso dispara el workflow y el post se publica solo.

```json
{
  "caption": "texto del post",
  "media": [
    {"path": "media/mi-post-1.jpg", "type": "IMAGE"},
    {"path": "media/mi-post-2.mp4", "type": "VIDEO"}
  ]
}
```

Tambien se puede lanzar a mano desde **Actions > Publish Instagram Carousel >
Run workflow**.

## Archivos

| Archivo | Que hace |
|---|---|
| `post-config.json` | El post a publicar: caption y lista de piezas. Es lo unico que se edita normalmente. |
| `media/` | Imagenes y videos, servidos por raw.githubusercontent.com. |
| `normalize_media.py` | Prepara los archivos antes de publicar (ver abajo). |
| `publish.py` | Valida, sube a Instagram y publica. |
| `published.json` | Registro de lo ya publicado. Lo escribe el robot. |
| `.github/workflows/publish-instagram.yml` | El workflow que orquesta todo. |
| `SETUP.md` | Detalles de la app de Meta, tokens y mantenimiento. |

## Que hace el robot

Antes de publicar nada:

- **Comprueba el token** contra la API. Si esta caducado o bloqueado, falla en
  2 segundos en vez de a mitad de la subida.
- **Arregla los videos sin audio.** Instagram rechaza los videos mudos en los
  carruseles, asi que si detecta uno le anade una pista en silencio y commitea
  el archivo corregido. No hay que acordarse de exportar con audio.
- **Avisa** si un video dura menos de 3s o mas de 60s, si la relacion de
  aspecto se sale de 0.80-1.91, o si las piezas no miden todas lo mismo.
- **Valida el post**: entre 2 y 10 piezas, caption de 2200 caracteres como
  maximo, 30 hashtags como maximo, sin rutas rotas ni archivos repetidos, y
  con extensiones que Instagram acepte.
- **Evita duplicados**: si ese mismo carrusel ya consta en `published.json`,
  no publica nada y termina en verde. Relanzar un run no duplica el post.
- **Espera al CDN**: comprueba que GitHub ya sirve la version correcta de cada
  archivo antes de pasarle las URLs a Instagram.

Al publicar espera de verdad a que cada pieza y el carrusel esten `FINISHED`
(no duerme unos segundos a ciegas) y reintenta solo los errores temporales de
Meta. Al terminar deja el media id y el enlace del post en el resumen del run.

## Republicar algo a proposito

Actions > Publish Instagram Carousel > Run workflow > marcar
**"Publicar aunque este post ya conste como publicado"**.
