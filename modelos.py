from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def omitir_propiedades_adicionales_del_esquema(
    esquema: dict[str, Any], modelo: type[BaseModel]
) -> None:
    esquema.pop("additionalProperties", None)


class Concepto(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=omitir_propiedades_adicionales_del_esquema,
    )

    termino: str = Field(description="Término importante identificado en los apuntes.")
    explicacion: str = Field(description="Explicación clara del término en el contexto de los apuntes.")


class Tarjeta(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=omitir_propiedades_adicionales_del_esquema,
    )

    pregunta: str = Field(description="Pregunta breve para repasar un contenido de los apuntes.")
    respuesta: str = Field(description="Respuesta correcta y concisa a la pregunta de repaso.")


class Pregunta(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=omitir_propiedades_adicionales_del_esquema,
    )

    enunciado: str = Field(description="Enunciado de una pregunta de opción múltiple sobre los apuntes.")
    opciones: list[str] = Field(description="Lista de opciones de respuesta para la pregunta.")
    correcta: int = Field(description="Índice, comenzando en 0, de la opción correcta dentro de la lista de opciones.")

    @field_validator("opciones")
    @classmethod
    def validar_opciones(cls, opciones: list[str]) -> list[str]:
        if len(opciones) != 4:
            raise ValueError(
                f"La pregunta debe tener exactamente 4 opciones; se recibieron {len(opciones)}."
            )

        opciones_normalizadas = [opcion.casefold() for opcion in opciones]
        if len(set(opciones_normalizadas)) != 4:
            raise ValueError("Las 4 opciones deben ser distintas, sin diferencias solo de mayúsculas y minúsculas.")

        return opciones

    @model_validator(mode="after")
    def validar_indice_correcta(self) -> "Pregunta":
        if not 0 <= self.correcta <= 3:
            raise ValueError(
                f"El índice de la opción correcta debe estar entre 0 y 3; se recibió {self.correcta}."
            )
        return self

class Apunte(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=omitir_propiedades_adicionales_del_esquema,
    )

    titulo: str = Field(description="Título breve que identifica el tema principal de la página.")
    materia: str = Field(description="Nombre de la materia a la que pertenecen los apuntes.")
    resumen: str = Field(description="Resumen claro de las ideas principales visibles en la página.")
    conceptos: list[Concepto] = Field(description="Lista de términos importantes con sus explicaciones.")
    tarjetas: list[Tarjeta] = Field(description="Lista de tarjetas de pregunta y respuesta para repasar.")
    examen: list[Pregunta] = Field(description="Lista de preguntas de opción múltiple basadas en los apuntes.")
    dificultad: int = Field(description="Nivel de dificultad estimado del contenido, expresado como número entero.")

    def a_markdown(self) -> str:
        guia = [
            f"# {self.titulo}",
            f"**Materia:** {self.materia}",
            f"**Dificultad:** {'⭐' * self.dificultad}{'☆' * (5 - self.dificultad)}",
            "",
            "## Resumen",
            self.resumen,
            "",
            "## Conceptos",
        ]
        guia.extend(
            f"- **{concepto.termino}:** {concepto.explicacion}"
            for concepto in self.conceptos
        )
        guia.extend(["", "## Tarjetas de repaso"])
        for indice, tarjeta in enumerate(self.tarjetas, start=1):
            guia.extend(
                [f"{indice}. **{tarjeta.pregunta}**", f"   - {tarjeta.respuesta}"]
            )

        guia.extend(["", "## Examen"])
        letras = ("a", "b", "c", "d")
        for indice, pregunta in enumerate(self.examen, start=1):
            guia.append(f"{indice}. {pregunta.enunciado}")
            for indice_opcion, opcion in enumerate(pregunta.opciones):
                marca = " **(Correcta)**" if indice_opcion == pregunta.correcta else ""
                guia.append(f"   {letras[indice_opcion]}) {opcion}{marca}")
            guia.append(
                f"   **Respuesta correcta:** {letras[pregunta.correcta]}) "
                f"{pregunta.opciones[pregunta.correcta]}"
            )

        return "\n".join(guia)


