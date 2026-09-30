import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Dashboard de Rutas Optimizadas",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ Dashboard de Rutas Optimizadas (OR-Tools + OSRM)")
st.markdown(
    "Visualización de rutas reales por red vial a partir de coordenadas"
    " optimizadas."
)

# ==========================================
# 2. CONTROL DE ACCESO (PASSWORD EN SIDEBAR)
# ==========================================
st.sidebar.header("🔐 Acceso Administrador")
clave_ingresada = st.sidebar.text_input(
    "Contraseña para ver datos extendidos:", type="password"
)

# Definimos la contraseña de acceso para el grupo autorizado
CLAVE_CORRECTA = "admin123"
es_admin = clave_ingresada == CLAVE_CORRECTA

if clave_ingresada and not es_admin:
    st.sidebar.error("Contraseña incorrecta")
elif es_admin:
    st.sidebar.success("Acceso concedido: Modo Avanzado Activo")

# ==========================================
# 3. DATOS DE ENTRADA (Coordenadas Optimizadas)
# ==========================================
puntos_optimizados = [
    [-0.180653, -78.467838],  # Parada 1: Depósito / Punto inicial
    [-0.175500, -78.472000],  # Parada 2
    [-0.168000, -78.465000],  # Parada 3
    [-0.160000, -78.478000],  # Parada 4
    [-0.155000, -78.470000],  # Parada 5: Punto final
]


# ==========================================
# 4. FUNCIÓN DE RUTEAMIENTO POR CALLES (OSRM)
# ==========================================
@st.cache_data
def obtener_geometria_ruta(puntos):
    coords_str = ";".join([f"{p[1]},{p[0]}" for p in puntos])
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
        else:
            return None, 0, 0
    except Exception:
        return None, 0, 0


linea_calles, distancia_total, duracion_total = obtener_geometria_ruta(
    puntos_optimizados
)

# ==========================================
# 5. DASHBOARD: MÉTRICAS BÁSICAS (Para todos)
# ==========================================
col1, col2, col3 = st.columns(3)
col1.metric("Total Paradas", len(puntos_optimizados))
col2.metric("Distancia Estimada", f"{distancia_total:.2f} km")
col3.metric("Tiempo de Recorrido", f"{duracion_total:.0f} min")

st.divider()

# ==========================================
# 6. CONSTRUCCIÓN DEL MAPA
# ==========================================
if linea_calles:
    mapa = folium.Map(
        location=puntos_optimizados[0], zoom_start=14, tiles="OpenStreetMap"
    )

    folium.PolyLine(
        locations=linea_calles,
        color="#2B579A",
        weight=6,
        opacity=0.85,
        tooltip=f"Ruta completa: {distancia_total:.2f} km (~{duracion_total:.0f} min)",
    ).add_to(mapa)

    for idx, punto in enumerate(puntos_optimizados):
        es_inicio = idx == 0
        es_fin = idx == len(puntos_optimizados) - 1

        color = "green" if es_inicio else ("red" if es_fin else "blue")
        etiqueta = (
            "Inicio / Depósito"
            if es_inicio
            else ("Fin de Ruta" if es_fin else f"Parada {idx + 1}")
        )

        folium.Marker(
            location=punto,
            popup=f"<b>{etiqueta}</b>",
            tooltip=etiqueta,
            icon=folium.Icon(color=color),
        ).add_to(mapa)

    st_folium(mapa, width="100%", height=500)

# ==========================================
# 7. SECCIÓN DE DATOS EXTENDIDOS (SOLO ADMINS)
# ==========================================
if es_admin:
    st.divider()
    st.subheader("📊 Reporte Detallado y Exportación (Datos Privados)")

    # Creamos un DataFrame con los datos completos de las paradas
    df_detalles = pd.DataFrame(
        {
            "Orden": [
                i + 1 for i in range(len(puntos_optimizados))
            ],  #[cite: 1]
            "Tipo": [
                "Depósito",
                "Cliente A",
                "Cliente B",
                "Cliente C",
                "Punto Entrega",
            ],
            "Latitud": [p[0] for p in puntos_optimizados],
            "Longitud": [p[1] for p in puntos_optimizados],
            "Volumen Carga (m³)": [0, 4.5, 2.1, 6.0, 0],
            "Tiempo de Espera (min)": [0, 15, 10, 20, 0],
        }
    )

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.dataframe(df_detalles, use_container_width=True)

    with col_b:
        st.write("**Resumen de Operación:**")
        st.write(
            f"• Carga total transportada: **{df_detalles['Volumen Carga (m³)'].sum()} m³**"
        )
        st.write(
            f"• Tiempo en paradas: **{df_detalles['Tiempo de Espera (min)'].sum()} min**"
        )

        # Botón para descargar el reporte
        csv = df_detalles.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Descargar Reporte CSV",
            data=csv,
            file_name="reporte_ruta_detallado.csv",
            mime="text/csv",
        )
