import folium
import pandas as pd
import requests
import streamlit as st
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from streamlit_folium import st_folium

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Dashboard de Rutas Optimizadas", page_icon="🗺️", layout="wide"
)

st.title("🗺️ Dashboard de Rutas Optimizadas (OR-Tools + OSRM)")
st.markdown(
    "Visualización y reoptimización de rutas por red vial en Quito (Sector Norte"
    " / Jipijapa / Batán / Parque Metropolitano)."
)

# ==========================================
# 2. CONTROL DE ACCESO Y OPCIONES EN SIDEBAR
# ==========================================
st.sidebar.header("🔐 Acceso Administrador")
clave_ingresada = st.sidebar.text_input(
    "Contraseña para ver datos extendidos:", type="password"
)

CLAVE_CORRECTA = "admin123"
es_admin = clave_ingresada == CLAVE_CORRECTA

if clave_ingresada and not es_admin:
    st.sidebar.error("Contraseña incorrecta")
elif es_admin:
    st.sidebar.success("Acceso concedido: Modo Avanzado Activo")

st.sidebar.divider()
st.sidebar.header("⚙️️ Estrategia de Ruteo")
modo_ruteo = st.sidebar.radio(
    "Selecciona la lógica de trazado:",
    (
        "Ruta Convencional (Estándar)",
        "Priorizar Avenidas Principales (Evitar calles residenciales)",
        "Reoptimizar Secuencia (OR-Tools)",
    ),
)

# ==========================================
# 3. DATOS DE ENTRADA (Coordenadas Quito Norte)
# ==========================================
# Coordenadas correspondientes a las paradas en el mapa del sector Jipijapa / Laureles / Metropolitano
paradas_originales = [
    [-0.1585, -78.4725],  # Parada 1: Depósito / Inicio (Sector Los Laureles / El Carmen) - Marcador Rojo
    [-0.1630, -78.4785],  # Parada 2: Las Acacias / Jipijapa - Marcador Azul Alto
    [-0.1690, -78.4705],  # Parada 3: Gabriel Marina / Miraflores - Marcador Azul Medio
    [-0.1785, -78.4740],  # Parada 4: Batán Bajo - Marcador Azul Bajo
    [-0.1830, -78.4720],  # Parada 5: Fin / Parque Metropolitano (Zona Sur) - Marcador Verde
]

# Puntos de paso por Avenidas Principales (Av. Eloy Alfaro / Av. 6 de Diciembre / Av. De los Granados)
waypoints_avenidas = [
    [-0.1590, -78.4700],  # Intersección Granados / Eloy Alfaro
    [-0.1670, -78.4740],  # Tramo fluido Av. 6 de Diciembre
    [-0.1750, -78.4760],  # Conexión Av. Eloy Alfaro / Batán
]


# ==========================================
# 4. SOLUCIONADOR OR-TOOLS (REOPTIMIZACIÓN DE SECUENCIA)
# ==========================================
def reoptimizar_con_ortools(puntos):
    """Aplica el algoritmo VRP de OR-Tools para encontrar la secuencia de paradas con menor costo."""
    # Matriz aproximada de distancias manhattan
    num_puntos = len(puntos)
    matriz_distancias = []
    for i in range(num_puntos):
        fila = []
        for j in range(num_puntos):
            d = abs(puntos[i][0] - puntos[j][0]) + abs(
                puntos[i][1] - puntos[j][1]
            )
            fila.append(int(d * 100000))
        matriz_distancias.append(fila)

    manager = pywrapcp.RoutingIndexManager(num_puntos, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return matriz_distancias[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        index = routing.Start(0)
        nueva_secuencia = []
        while not routing.IsEnd(index):
            nodo = manager.IndexToNode(index)
            nueva_secuencia.append(puntos[nodo])
            index = solution.Value(routing.NextVar(index))
        return nueva_secuencia
    return puntos


# ==========================================
# 5. OBTENER TRAZADO VIAL DESDE OSRM
# ==========================================
@st.cache_data
def obtener_geometria_osrm(puntos_secuencia):
    coords_str = ";".join([f"{p[1]},{p[0]}" for p in puntos_secuencia])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("code") == "Ok":
            geometria = [
                [coord[1], coord[0]]
                for coord in data["routes"][0]["geometry"]["coordinates"]
            ]
            distancia_km = data["routes"][0]["distance"] / 1000.0
            duracion_min = data["routes"][0]["duration"] / 60.0
            return geometria, distancia_km, duracion_min
        return None, 0, 0
    except Exception:
        return None, 0, 0


# Procesar según la opción seleccionada
if modo_ruteo == "Reoptimizar Secuencia (OR-Tools)":
    puntos_a_procesar = reoptimizar_con_ortools(paradas_originales)
elif modo_ruteo == "Priorizar Avenidas Principales (Evitar calles residenciales)":
    # Intercalar waypoints por avenidas principales
    puntos_a_procesar = [
        paradas_originales[0],
        waypoints_avenidas[0],
        paradas_originales[1],
        waypoints_avenidas[1],
        paradas_originales[2],
        paradas_originales[3],
        waypoints_avenidas[2],
        paradas_originales[4],
    ]
else:
    puntos_a_procesar = paradas_originales

linea_calles, distancia_total, duracion_total = obtener_geometria_osrm(
    puntos_a_procesar
)

# ==========================================
# 6. DASHBOARD: MÉTRICAS Y MAPA
# ==========================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("Paradas Totales", len(paradas_originales))
col2.metric("Distancia Estimada", f"{distancia_total:.2f} km")
col3.metric("Tiempo de Recorrido", f"{duracion_total:.0f} min")
col4.metric("Estrategia", modo_ruteo.split(" ")[0])

st.divider()

if linea_calles:
    mapa = folium.Map(
        location=paradas_originales[0], zoom_start=14, tiles="OpenStreetMap"
    )

    color_linea = (
        "#107C41"
        if modo_ruteo.startswith("Priorizar")
        else ("#D83B01" if modo_ruteo.startswith("Reoptimizar") else "#2B579A")
    )

    folium.PolyLine(
        locations=linea_calles,
        color=color_linea,
        weight=6,
        opacity=0.85,
        tooltip=f"Ruta completa: {distancia_total:.2f} km (~{duracion_total:.0f} min)",
    ).add_to(mapa)

    # Marcadores de paradas reales
    for idx, punto in enumerate(paradas_originales):
        es_inicio = idx == 0
        es_fin = idx == len(paradas_originales) - 1

        color_pin = "green" if es_inicio else ("red" if es_fin else "blue")
        etiqueta = (
            "Inicio / Depósito"
            if es_inicio
            else ("Fin de Ruta" if es_fin else f"Parada {idx + 1}")
        )

        folium.Marker(
            location=punto,
            popup=f"<b>{etiqueta}</b><br>Coordenadas: {punto[0]}, {punto[1]}",
            tooltip=etiqueta,
            icon=folium.Icon(color=color_pin, icon="info-sign"),
        ).add_to(mapa)

    st_folium(mapa, width="100%", height=550)

# ==========================================
# 7. SECCIÓN DE DATOS EXTENDIDOS (SOLO ADMINS)
# ==========================================
if es_admin:
    st.divider()
    st.subheader("📊 Reporte Detallado de Operación (Datos Privados)")

    df_detalles = pd.DataFrame(
        {
            "Orden": [i + 1 for i in range(len(paradas_originales))],
            "Ubicación / Sector": [
                "Depósito Los Laureles",
                "Cliente Jipijapa",
                "Punto Miraflores / Gabriel Marina",
                "Cliente Batán Bajo",
                "Descarga Metropolitano",
            ],
            "Latitud": [p[0] for p in paradas_originales],
            "Longitud": [p[1] for p in paradas_originales],
            "Volumen Carga (m³)": [0, 4.5, 2.1, 6.0, 0],
            "Tiempo en Parada (min)": [0, 15, 10, 20, 0],
        }
    )

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.dataframe(df_detalles, use_container_width=True)

    with col_b:
        st.write("**Métricas Privadas de Operación:**")
        st.write(
            f"• Carga total transportada: **{df_detalles['Volumen Carga (m³)'].sum()} m³**"
        )
        st.write(
            f"• Tiempo de atención total: **{df_detalles['Tiempo en Parada (min)'].sum()} min**"
        )

        csv = df_detalles.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Descargar Reporte CSV",
            data=csv,
            file_name="reporte_ruta_quito_detallado.csv",
            mime="text/csv",
        )
