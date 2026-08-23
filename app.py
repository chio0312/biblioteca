from flask import Flask, render_template, request, redirect, url_for, session
from libros import LIBROS
import sqlite3
import secrets
from datetime import datetime


app = Flask(__name__)

app.secret_key = "clave-biblioteca-2026"

DATABASE = "biblioteca.db"

ADMIN_PASSWORD = "biblioteca123"


# ==========================================
# CONEXIÓN CON LA BASE DE DATOS
# ==========================================

def conectar():

    conexion = sqlite3.connect(DATABASE)

    conexion.row_factory = sqlite3.Row

    return conexion


# ==========================================
# CREAR BASE DE DATOS
# ==========================================

def crear_base_datos():

    conexion = conectar()

    conexion.execute("""
        CREATE TABLE IF NOT EXISTS prestamos (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

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

    conexion.close()


crear_base_datos()


# ==========================================
# EJEMPLARES DISPONIBLES
# ==========================================

def disponibles(indice):

    conexion = conectar()

    prestados = conexion.execute(
        """
        SELECT COUNT(*)

        FROM prestamos

        WHERE libro = ?

        AND estado IN ('prestado', 'pendiente')
        """,
        (indice,)
    ).fetchone()[0]

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

        existe = conexion.execute(
            """
            SELECT id

            FROM prestamos

            WHERE codigo = ?
            """,
            (codigo,)
        ).fetchone()

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

        conexion.execute(
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

            VALUES (?, ?, ?, ?, 'pendiente', 0, ?)
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

        resultados = conexion.execute(
            """
            SELECT *

            FROM prestamos

            WHERE codigo = ?
            """,
            (codigo,)
        ).fetchall()

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

    conexion.execute(
        """
        UPDATE prestamos

        SET devolucion_solicitada = 1

        WHERE id = ?

        AND estado = 'prestado'
        """,
        (id,)
    )

    conexion.commit()

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

    conexion.execute(
        """
        UPDATE prestamos

        SET estado = 'prestado'

        WHERE id = ?

        AND estado = 'pendiente'
        """,
        (id,)
    )

    conexion.commit()

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

    conexion.execute(
        """
        DELETE FROM prestamos

        WHERE id = ?

        AND estado = 'pendiente'
        """,
        (id,)
    )

    conexion.commit()

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

    prestamos = conexion.execute(
        """
        SELECT *

        FROM prestamos

        WHERE estado IN ('pendiente', 'prestado')

        ORDER BY id DESC
        """
    ).fetchall()

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

    conexion.execute(
        """
        UPDATE prestamos

        SET estado = 'devuelto',

            devolucion_solicitada = 0

        WHERE id = ?
        """,
        (id,)
    )

    conexion.commit()

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

    app.run(debug=True)