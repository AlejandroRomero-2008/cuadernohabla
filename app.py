import streamlit as st

from cerebro import (
    RespuestaGeminiInvalida,
    ServicioGeminiOcupado,
    analizar_pagina,
    calificar,
    crear_cliente,
    decir,
    generar_imagen_referencia,
)


TITULO_PAGINA = "Mi cuaderno habla"


st.set_page_config(
    page_title=TITULO_PAGINA,
    page_icon="📓",
    layout="centered",
)

try:
    llave_api = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error(
        "Falta la llave de Gemini. Agregala en el archivo "
        "`.streamlit/secrets.toml` con esta línea: "
        '`GEMINI_API_KEY = "tu_llave"`.'
    )
    st.stop()

# Streamlit vuelve a ejecutar el archivo con cada interacción; la sesión conserva el apunte y el avance.
if "apunte" not in st.session_state:
    st.session_state.apunte = None
if "respuestas_examen" not in st.session_state:
    st.session_state.respuestas_examen = {}
if "examen_entregado" not in st.session_state:
    st.session_state.examen_entregado = False
if "audio_resumen" not in st.session_state:
    st.session_state.audio_resumen = None
if "audio_resumen_intentado" not in st.session_state:
    st.session_state.audio_resumen_intentado = False
if "imagen_referencia" not in st.session_state:
    st.session_state.imagen_referencia = None
if "imagen_referencia_mime" not in st.session_state:
    st.session_state.imagen_referencia_mime = "image/png"
if "imagen_referencia_no_disponible" not in st.session_state:
    st.session_state.imagen_referencia_no_disponible = False
if "imagen_referencia_mensaje" not in st.session_state:
    st.session_state.imagen_referencia_mensaje = (
        "No se pudo crear la infografía. Probá de nuevo."
    )


def procesar_imagen(archivo) -> None:
    if archivo is None:
        st.warning("Primero tomá una foto o seleccioná una imagen de la página.")
        return

    try:
        with st.spinner("Analizando la página..."):
            cliente = crear_cliente(llave_api)
            apunte = analizar_pagina(
                datos_imagen=archivo.getvalue(),
                tipo_mime=archivo.type,
                cliente=cliente,
            )
        for clave in list(st.session_state):
            if clave.startswith("respuesta_examen_"):
                del st.session_state[clave]
        st.session_state.apunte = apunte
        st.session_state.respuestas_examen = {}
        st.session_state.examen_entregado = False
        st.session_state.audio_resumen = None
        st.session_state.audio_resumen_intentado = False
        st.session_state.imagen_referencia = None
        st.session_state.imagen_referencia_mime = "image/png"
        st.session_state.imagen_referencia_no_disponible = False
        st.session_state.imagen_referencia_mensaje = (
            "No se pudo crear la infografía. Probá de nuevo."
        )
    except ServicioGeminiOcupado as error:
        st.warning(str(error))
    except RespuestaGeminiInvalida as error:
        st.warning(str(error))
    except Exception as error:
        st.error(f"No se pudo analizar la página. Probá de nuevo. Detalle: {error}")


st.title(TITULO_PAGINA)

pestana_foto, pestana_subir = st.tabs(["Tomar foto", "Subir imagen"])

with pestana_foto:
    foto = st.camera_input("Tomá una foto de la página")
    if st.button("Analizar la página", key="analizar_foto"):
        procesar_imagen(foto)

with pestana_subir:
    imagen_subida = st.file_uploader(
        "Seleccioná una imagen de la página",
        type=["png", "jpg", "jpeg", "webp"],
    )
    if st.button("Analizar la página", key="analizar_archivo"):
        procesar_imagen(imagen_subida)

apunte = st.session_state.apunte
if apunte is not None:
    st.header(apunte.titulo)
    st.subheader(apunte.materia)
    st.markdown(f"**Dificultad:** {'⭐' * apunte.dificultad} ({apunte.dificultad}/5)")

    st.subheader("Resumen")
    st.write(apunte.resumen)

    escuchar_resumen = st.toggle("🔊 Escuchar el resumen")
    if escuchar_resumen:
        if not st.session_state.audio_resumen_intentado:
            try:
                st.session_state.audio_resumen = decir(
                    apunte.titulo,
                    apunte.resumen,
                    crear_cliente(llave_api),
                )
            except Exception:
                st.session_state.audio_resumen = None
            st.session_state.audio_resumen_intentado = True

        if st.session_state.audio_resumen:
            st.audio(st.session_state.audio_resumen, format="audio/mp3")
        else:
            st.caption("La voz no está disponible en este momento.")
    elif st.session_state.audio_resumen is None:
        st.session_state.audio_resumen_intentado = False

    st.subheader("Conceptos")
    for concepto in apunte.conceptos:
        st.markdown(f"- **{concepto.termino}:** {concepto.explicacion}")

    st.subheader("Tarjetas de repaso")
    for indice, tarjeta in enumerate(apunte.tarjetas):
        with st.expander(tarjeta.pregunta):
            st.write(tarjeta.respuesta)

    st.subheader("Examen")
    for indice, pregunta in enumerate(apunte.examen):
        opcion_elegida = st.radio(
            pregunta.enunciado,
            options=pregunta.opciones,
            index=None,
            key=f"respuesta_examen_{indice}",
            disabled=st.session_state.examen_entregado,
        )
        if opcion_elegida is not None:
            st.session_state.respuestas_examen[indice] = pregunta.opciones.index(opcion_elegida)

        if st.session_state.examen_entregado:
            indice_elegido = st.session_state.respuestas_examen.get(indice)
            if indice_elegido == pregunta.correcta:
                st.success("¡Correcto!")
            elif indice_elegido is None:
                st.warning(f"Sin respuesta. La opción correcta era: {pregunta.opciones[pregunta.correcta]}")
            else:
                st.error(
                    f"Incorrecto. La opción correcta era: {pregunta.opciones[pregunta.correcta]}"
                )

    if not st.session_state.examen_entregado:
        if st.button("Entregar examen"):
            st.session_state.examen_entregado = True
            st.rerun()
    else:
        aciertos, total = calificar(apunte, st.session_state.respuestas_examen)
        st.metric("Puntaje", f"{aciertos} / {total}")
        if aciertos == total:
            st.balloons()

    st.download_button(
        "Descargar guía de estudio",
        data=apunte.a_markdown(),
        file_name="guia_de_estudio.md",
        mime="text/markdown",
    )

    st.subheader("Imagen de referencia")
    if st.session_state.imagen_referencia is None:
        if st.button("Crear infografía gratuita", key="generar_imagen_referencia"):
            with st.spinner("Generando imagen de referencia..."):
                try:
                    resultado_imagen = generar_imagen_referencia(apunte)
                except Exception:
                    resultado_imagen = None
            if resultado_imagen is None:
                st.session_state.imagen_referencia_no_disponible = True
            else:
                (
                    st.session_state.imagen_referencia,
                    st.session_state.imagen_referencia_mime,
                ) = resultado_imagen

    if st.session_state.imagen_referencia:
        st.image(
            st.session_state.imagen_referencia,
            caption="Infografía creada desde el apunte. Hacé clic para ampliar.",
            use_container_width=True,
        )
        extension = (
            "jpg"
            if st.session_state.imagen_referencia_mime == "image/jpeg"
            else "png"
        )
        st.download_button(
            "Descargar imagen",
            data=st.session_state.imagen_referencia,
            file_name=f"imagen_de_referencia.{extension}",
            mime=st.session_state.imagen_referencia_mime,
        )
    elif st.session_state.imagen_referencia_no_disponible:
        st.caption(st.session_state.imagen_referencia_mensaje)
