from flask import Flask, render_template, request, redirect, url_for, session
from libros import LIBROS
import psycopg2
import psycopg2.extras
import secrets
import os
from datetime import datetime


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "clave-local-biblioteca"
)

DATABASE_URL = os.environ.get("DATABASE_URL")


ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "biblioteca123"
)


# ==========================================
# CONEXIÓN CON LA BASE DE DATOS
# ==========================================

def conectar():

    conexion = psycopg2.connect(DATABASE_URL)

    return conexion


# ==========================================
# CREAR BASE DE DATOS
# ==========================================

def crear_base_datos():

    conexion = conectar()

    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prestamos (

            id SERIAL PRIMARY KEY,

            codigo TEXT UNIQUE NOT NULL,

            libro INTEGER NOT NULL,

            nombre TEXT NOT NULL,

            grado TEXT NOT NULL,

            estado TEXT NOT NULL DEFAULT 'pendiente',

            devolucion_solicitada INTEGER DEFAULT 0,

            fecha TEXT NOT NULL

        )
    """)

    conexion.commit()

    cursor.close()

    conexion.close()


# Solo crear la tabla cuando exista una conexión
if DATABASE_URL:
    crear_base_datos()


# ==========================================
# EJEMPLARES DISPONIBLES
# ==========================================

def disponibles(indice):

    conexion = conectar()

    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)

        FROM prestamos

        WHERE libro = %s

        AND estado IN ('prestado', 'pendiente')
        """,
        (indice,)
    )

    prestados = cursor.fetchone()[0]

    cursor.close()

    conexion.close()

    total = LIBROS[indice]["ejemplares"]

    return max(0, total - prestados)


# ==========================================
# GENERAR CÓDIGO DE PRÉSTAMO
# ==========================================

def generar_codigo():

    while True:

        codigo = "BIB-" + secrets.token_hex(3).upper()

        conexion = conectar()

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT id

            FROM prestamos

            WHERE codigo = %s
            """,
            (codigo,)
        )

        existe = cursor.fetchone()

        cursor.close()

        conexion.close()

        if not existe:

            return codigo


# ==========================================
# PÁGINA PRINCIPAL
# ==========================================

@app.route("/")
def inicio():

    categorias = {}

    for indice, libro in enumerate(LIBROS):

        libro_copia = libro.copy()

        libro_copia["indice"] = indice

        libro_copia["disponibles"] = disponibles(indice)

        categoria = libro["categoria"]

        if categoria not in categorias:

            categorias[categoria] = []

        categorias[categoria].append(libro_copia)


    busqueda = request.args.get(
        "buscar",
        ""
    ).strip().lower()


    resultados = []


    if busqueda:

        for indice, libro in enumerate(LIBROS):

            if (
                busqueda in libro["titulo"].lower()
                or
                busqueda in libro["autor"].lower()
                or
                busqueda in libro["categoria"].lower()
            ):

                libro_copia = libro.copy()

                libro_copia["indice"] = indice

                libro_copia["disponibles"] = disponibles(indice)

                resultados.append(libro_copia)


    return render_template(
        "index.html",
        categorias=categorias,
        resultados=resultados,
        busqueda=busqueda,
        total=len(LIBROS)
    )


# ==========================================
# CATEGORÍA
# ==========================================

@app.route("/categoria/<nombre>")
def categoria(nombre):

    libros_categoria = []

    for indice, libro in enumerate(LIBROS):

        if libro["categoria"] == nombre:

            libro_copia = libro.copy()

            libro_copia["indice"] = indice

            libro_copia["disponibles"] = disponibles(indice)

            libros_categoria.append(libro_copia)


    return render_template(
        "categoria.html",
        categoria=nombre,
        libros=libros_categoria
    )


# ==========================================
# VER LIBRO
# ==========================================

@app.route("/libro/<int:indice>")
def ver_libro(indice):

    if indice < 0 or indice >= len(LIBROS):

        return "Libro no encontrado", 404


    libro = LIBROS[indice]

    cantidad_disponible = disponibles(indice)


    return render_template(
        "libro.html",
        libro=libro,
        indice=indice,
        disponibles=cantidad_disponible
    )


# ==========================================
# SOLICITAR LIBRO
# ==========================================

@app.route(
    "/solicitar/<int:indice>",
    methods=["GET", "POST"]
)
def solicitar(indice):

    if indice < 0 or indice >= len(LIBROS):

        return "Libro no encontrado", 404


    libro = LIBROS[indice]

    cantidad_disponible = disponibles(indice)


    if request.method == "POST":

        nombre = request.form["nombre"].strip()

        grado = request.form["grado"].strip()


        if cantidad_disponible <= 0:

            return "Este libro no está disponible."


        codigo = generar_codigo()


        conexion = conectar()

        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO prestamos
            (
                codigo,
                libro,
                nombre,
                grado,
                estado,
                devolucion_solicitada,
                fecha
            )

            VALUES (%s, %s, %s, %s, 'pendiente', 0, %s)
            """,
            (
                codigo,
                indice,
                nombre,
                grado,
                datetime.now().strftime(
                    "%d/%m/%Y %H:%M"
                )
            )
        )

        conexion.commit()

        cursor.close()

        conexion.close()


        return render_template(
            "solicitud_exitosa.html",
            libro=libro,
            nombre=nombre,
            grado=grado,
            codigo=codigo
        )


    return render_template(
        "solicitar.html",
        libro=libro,
        indice=indice,
        disponibles=cantidad_disponible
    )


# ==========================================
# MIS PRÉSTAMOS
# ==========================================

@app.route(
    "/mis-prestamos",
    methods=["GET", "POST"]
)
def mis_prestamos():

    resultados = []

    codigo = ""


    if request.method == "POST":

        codigo = request.form["codigo"].strip().upper()


        conexion = conectar()

        cursor = conexion.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        cursor.execute(
            """
            SELECT *

            FROM prestamos

            WHERE codigo = %s
            """,
            (codigo,)
        )

        resultados = cursor.fetchall()

        cursor.close()

        conexion.close()


    return render_template(
        "mis_prestamos.html",
        prestamos=resultados,
        libros=LIBROS,
        codigo=codigo
    )


# ==========================================
# SOLICITAR DEVOLUCIÓN
# ==========================================

@app.route(
    "/solicitar-devolucion/<int:id>",
    methods=["POST"]
)
def solicitar_devolucion(id):

    conexion = conectar()

    cursor = conexion.cursor()

    cursor.execute(
        """
        UPDATE prestamos

        SET devolucion_solicitada = 1

        WHERE id = %s

        AND estado = 'prestado'
        """,
        (id,)
    )

    conexion.commit()

    cursor.close()

    conexion.close()


    return redirect(
        url_for("mis_prestamos")
    )


# ==========================================
# CONFIRMAR ENTREGA DEL LIBRO
# ==========================================

@app.route(
    "/confirmar-entrega/<int:id>",
    methods=["POST"]
)
def confirmar_entrega(id):

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    conexion = conectar()

    cursor = conexion.cursor()

    cursor.execute(
        """
        UPDATE prestamos

        SET estado = 'prestado'

        WHERE id = %s

        AND estado = 'pendiente'
        """,
        (id,)
    )

    conexion.commit()

    cursor.close()

    conexion.close()


    return redirect(
        url_for("admin")
    )


# ==========================================
# RECHAZAR SOLICITUD
# ==========================================

@app.route(
    "/rechazar-solicitud/<int:id>",
    methods=["POST"]
)
def rechazar_solicitud(id):

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    conexion = conectar()

    cursor = conexion.cursor()

    cursor.execute(
        """
        DELETE FROM prestamos

        WHERE id = %s

        AND estado = 'pendiente'
        """,
        (id,)
    )

    conexion.commit()

    cursor.close()

    conexion.close()


    return redirect(
        url_for("admin")
    )


# ==========================================
# LOGIN ADMINISTRADOR
# ==========================================

@app.route(
    "/admin-login",
    methods=["GET", "POST"]
)
def admin_login():

    error = None


    if request.method == "POST":

        password = request.form["password"]


        if password == ADMIN_PASSWORD:

            session["admin"] = True

            return redirect(
                url_for("admin")
            )


        error = "Contraseña incorrecta."


    return render_template(
        "admin_login.html",
        error=error
    )


# ==========================================
# PANEL ADMINISTRADOR
# ==========================================

@app.route("/admin")
def admin():

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    conexion = conectar()

    cursor = conexion.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    )

    cursor.execute(
        """
        SELECT *

        FROM prestamos

        WHERE estado IN ('pendiente', 'prestado')

        ORDER BY id DESC
        """
    )

    prestamos = cursor.fetchall()

    cursor.close()

    conexion.close()


    return render_template(
        "admin.html",
        prestamos=prestamos,
        libros=LIBROS
    )


# ==========================================
# CONFIRMAR DEVOLUCIÓN
# ==========================================

@app.route(
    "/confirmar-devolucion/<int:id>",
    methods=["POST"]
)
def confirmar_devolucion(id):

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    conexion = conectar()

    cursor = conexion.cursor()

    cursor.execute(
        """
        UPDATE prestamos

        SET estado = 'devuelto',

            devolucion_solicitada = 0

        WHERE id = %s
        """,
        (id,)
    )

    conexion.commit()

    cursor.close()

    conexion.close()


    return redirect(
        url_for("admin")
    )


# ==========================================
# CERRAR SESIÓN
# ==========================================

@app.route("/admin-logout")
def admin_logout():

    session.pop("admin", None)

    return redirect(
        url_for("inicio")
    )


# ==========================================
# INICIAR SERVIDOR
# ==========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )