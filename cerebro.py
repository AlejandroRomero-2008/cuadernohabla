import base64
import json
import subprocess
import time
from io import BytesIO
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
from google.genai import Client, errors, types
from pydantic import ValidationError

from modelos import Apunte


MODELOS = ("gemini-3.5-flash-lite", "gemini-3.6-flash")
INTENTOS_POR_MODELO = 2
INSTRUCCION_SISTEMA = (
    "Actuá como un profesor paciente de bachillerato de El Salvador y escribí siempre "
    "en español salvadoreño claro. Basate únicamente en lo que se ve en la imagen; "
    "no inventés temas. Si la foto está borrosa, decilo en el resumen en vez de "
    "inventar contenido. Creá opciones incorrectas de examen creíbles, no absurdas, "
    "y variá entre preguntas la posición de la respuesta correcta."
)
MENSAJE_RESPUESTA_INVALIDA = (
    "Gemini no pudo organizar el apunte. Probá analizar la página otra vez."
)


class RespuestaGeminiInvalida(Exception):
    """Indica que la respuesta de Gemini no coincide con el formato esperado."""


class ServicioGeminiOcupado(Exception):
    """Indica que Gemini sigue temporalmente saturado tras varios intentos."""


def crear_cliente(api_key: str) -> Client:
    if not api_key or not api_key.strip():
        raise ValueError("La llave de acceso no puede estar vacía.")
    return Client(api_key=api_key)


def decir(titulo: str, resumen: str, cliente: Client) -> bytes | None:
    respuesta = cliente.interactions.create(
        model="gemini-3.8-flash-tts",
        input=[
            {
                "type": "user_input",
                "content": [
                    {
                        "type": "text",
                        "text": f"{titulo}. {resumen}",
                        "annotations": [
                            {
                                "type": "speech_metadata",
                                "style": "warm and clear Spanish narration",
                            }
                        ],
                    }
                ],
            }
        ],
        response_format={"type": "audio", "mime_type": "audio/wav"},
        generation_config={"speech_config": [{"voice": "Kore"}]},
    )
    if not respuesta.output_audio or not respuesta.output_audio.data:
        return None

    audio_wav = base64.b64decode(respuesta.output_audio.data)
    conversion = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-codec:a",
            "libmp3lame",
            "-f",
            "mp3",
            "pipe:1",
        ],
        input=audio_wav,
        capture_output=True,
        check=True,
    )
    return conversion.stdout or None


def generar_imagen_referencia(apunte: Apunte) -> tuple[bytes, str]:
    ancho, alto = 1440, 1080
    fondo = "#F4F6EF"
    tinta = "#183B3A"
    colores = ("#23847D", "#E47C58", "#D5A52D", "#5278A4", "#6B936B", "#B25F76")
    imagen = Image.new("RGB", (ancho, alto), fondo)
    dibujo = ImageDraw.Draw(imagen)

    rutas_fuentes = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )

    def fuente(tamano: int, negrita: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for ruta in rutas_fuentes:
            if ruta.is_file():
                candidata = ruta.with_name("arialbd.ttf") if negrita and ruta.name == "arial.ttf" else ruta
                if candidata.is_file():
                    return ImageFont.truetype(str(candidata), tamano)
                return ImageFont.truetype(str(ruta), tamano)
        try:
            return ImageFont.load_default(size=tamano)
        except TypeError:
            return ImageFont.load_default()

    def envolver(texto: str, letra: ImageFont.FreeTypeFont | ImageFont.ImageFont, ancho_maximo: int) -> list[str]:
        lineas = []
        linea = ""
        for palabra in texto.split():
            candidata = f"{linea} {palabra}".strip()
            if linea and dibujo.textbbox((0, 0), candidata, font=letra)[2] > ancho_maximo:
                lineas.append(linea)
                linea = palabra
            else:
                linea = candidata
        if linea:
            lineas.append(linea)
        return lineas

    dibujo.rectangle((0, 0, ancho, 228), fill=tinta)
    dibujo.text((72, 42), apunte.materia.upper(), font=fuente(24, True), fill="#93D1C4")
    letra_titulo = fuente(54, True)
    titulo = envolver(apunte.titulo, letra_titulo, ancho - 144)[:2]
    for indice, linea in enumerate(titulo):
        dibujo.text((72, 86 + indice * 66), linea, font=letra_titulo, fill="#FFFFFF")

    dibujo.rounded_rectangle((72, 266, ancho - 72, 420), radius=24, fill="#FFFFFF")
    dibujo.rounded_rectangle((72, 266, 86, 420), radius=7, fill=colores[0])
    dibujo.text((112, 288), "IDEA PRINCIPAL", font=fuente(20, True), fill=colores[0])
    letra_resumen = fuente(25)
    resumen = envolver(apunte.resumen, letra_resumen, ancho - 224)[:3]
    for indice, linea in enumerate(resumen):
        dibujo.text((112, 326 + indice * 34), linea, font=letra_resumen, fill=tinta)

    dibujo.text((72, 458), "Conceptos clave", font=fuente(30, True), fill=tinta)
    conceptos = apunte.conceptos[:6]
    if not conceptos:
        dibujo.text((72, 512), "Revisá el resumen para recordar las ideas principales.", font=fuente(24), fill=tinta)

    margen = 72
    espacio = 24
    ancho_tarjeta = (ancho - 2 * margen - espacio) // 2
    alto_tarjeta = 166
    inicio_y = 510
    for indice, concepto in enumerate(conceptos):
        columna = indice % 2
        fila = indice // 2
        x = margen + columna * (ancho_tarjeta + espacio)
        y = inicio_y + fila * (alto_tarjeta + 22)
        color = colores[indice % len(colores)]
        dibujo.rounded_rectangle(
            (x, y, x + ancho_tarjeta, y + alto_tarjeta),
            radius=20,
            fill="#FFFFFF",
            outline="#E0E6DD",
            width=2,
        )
        dibujo.ellipse((x + 22, y + 22, x + 70, y + 70), fill=color)
        dibujo.text((x + 39, y + 29), str(indice + 1), font=fuente(24, True), fill="#FFFFFF")
        letra_concepto = fuente(23, True)
        for linea_indice, linea in enumerate(envolver(concepto.termino, letra_concepto, ancho_tarjeta - 116)[:2]):
            dibujo.text((x + 88, y + 25 + linea_indice * 30), linea, font=letra_concepto, fill=tinta)
        letra_explicacion = fuente(20)
        explicacion = envolver(concepto.explicacion, letra_explicacion, ancho_tarjeta - 48)[:3]
        for linea_indice, linea in enumerate(explicacion):
            dibujo.text((x + 24, y + 88 + linea_indice * 27), linea, font=letra_explicacion, fill="#425956")

    salida = BytesIO()
    imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue(), "image/png"


def analizar_pagina(datos_imagen: bytes, tipo_mime: str, cliente: Client) -> Apunte:
    if not datos_imagen:
        raise ValueError("La imagen está vacía; seleccioná una foto de la página.")

    contenidos = [
        types.Part.from_bytes(data=datos_imagen, mime_type=tipo_mime),
        "Analizá esta página y prepará el apunte solicitado.",
    ]
    configuracion = types.GenerateContentConfig(
        system_instruction=INSTRUCCION_SISTEMA,
        response_mime_type="application/json",
        response_json_schema=Apunte.model_json_schema(),
        temperature=0.4,
    )

    respuesta = None
    ultimo_error = None
    for modelo in MODELOS:
        for intento in range(INTENTOS_POR_MODELO):
            try:
                respuesta = cliente.models.generate_content(
                    model=modelo,
                    contents=contenidos,
                    config=configuracion,
                )
                break
            except errors.ServerError as error:
                if error.code not in (500, 502, 503, 504):
                    raise
                ultimo_error = error
                if intento + 1 < INTENTOS_POR_MODELO:
                    time.sleep(1)
        if respuesta is not None:
            break

    if respuesta is None:
        raise ServicioGeminiOcupado(
            "Gemini no está disponible por el momento. Esperá un poco y probá de nuevo."
        ) from ultimo_error

    if isinstance(respuesta.parsed, Apunte):
        return respuesta.parsed

    if respuesta.parsed:
        try:
            return Apunte.model_validate(respuesta.parsed)
        except ValidationError as error:
            raise RespuestaGeminiInvalida(MENSAJE_RESPUESTA_INVALIDA) from error

    try:
        contenido = json.loads(respuesta.text)
        return Apunte.model_validate(contenido)
    except (json.JSONDecodeError, TypeError, ValidationError) as error:
        raise RespuestaGeminiInvalida(MENSAJE_RESPUESTA_INVALIDA) from error


def calificar(apunte: Apunte, respuestas: dict[int, int]) -> tuple[int, int]:
    aciertos = sum(
        respuestas.get(indice) == pregunta.correcta
        for indice, pregunta in enumerate(apunte.examen)
    )
    return aciertos, len(apunte.examen)
