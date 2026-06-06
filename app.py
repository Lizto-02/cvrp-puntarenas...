import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="CVRP · Florida Bebidas · Puntarenas",
    page_icon="🍺",
    layout="wide"
)

# ── Datos ────────────────────────────────────────────────────
CANTONES = [
    "CD Puntarenas","Puntarenas","Esparza","Buenos Aires",
    "Montes de Oro","Osa","Quepos","Golfito","Coto Brus",
    "Parrita","Corredores","Garabito","Monteverde","Puerto Jiménez",
]
DEMANDA = [0,107,27,37,12,28,24,33,35,16,39,20,4,8]
COORDS = {
    "CD Puntarenas": (9.9760,-84.8381),
    "Puntarenas":    (9.9760,-84.8381),
    "Esparza":       (9.9882,-84.6648),
    "Buenos Aires":  (9.1647,-83.3308),
    "Montes de Oro": (10.0831,-84.6519),
    "Osa":           (8.9134,-83.4710),
    "Quepos":        (9.4317,-84.1631),
    "Golfito":       (8.6480,-83.1820),
    "Coto Brus":     (8.9398,-82.9640),
    "Parrita":       (9.5175,-84.3261),
    "Corredores":    (8.6098,-82.9860),
    "Garabito":      (9.6315,-84.6476),
    "Monteverde":    (10.2995,-84.8247),
    "Puerto Jiménez":(8.5329,-83.3004),
}
DISTANCIAS = [
    [  0,  0, 25,244, 27,243,124,307,307, 99,332, 60, 47,303],
    [  0,  0, 25,244, 27,243,124,307,307, 99,332, 60, 47,303],
    [ 25, 25,  0,224, 19,226,109,290,287, 85,314, 55, 49,288],
    [244,244,224,  0,240, 41,124, 80, 63,150, 95,196,267, 92],
    [ 27, 27, 19,240,  0,244,127,308,303,103,331, 73, 30,305],
    [243,243,226, 41,244,  0,119, 64, 79,145, 90,189,272, 64],
    [124,124,109,124,127,119,  0,183,186, 26,208, 72,156,179],
    [307,307,290, 80,308, 64,183,  0, 54,208, 31,253,336, 25],
    [307,307,287, 63,303, 79,186, 54,  0,212, 46,259,330, 78],
    [ 99, 99, 85,150,103,145, 26,208,212,  0,234, 47,133,204],
    [332,332,314, 95,331, 90,208, 31, 46,234,  0,279,359, 52],
    [ 60, 60, 55,196, 73,189, 72,253,259, 47,279,  0,102,246],
    [ 47, 47, 49,267, 30,272,156,336,330,133,359,102,  0,335],
    [303,303,288, 92,305, 64,179, 25, 78,204, 52,246,335,  0],
]

CAPACIDAD   = 24
JORNADA_MIN = 480
RECARGA_MIN = 20
VEL_KMH     = 40
MIN_PARADA  = 15
MIN_PALLET  = 3

COLORES = [
    "#E63946","#2A9D8F","#E9C46A","#F4A261","#264653",
    "#6A4C93","#1982C4","#8AC926","#FF595E","#6A0572",
    "#3A86FF","#FB5607","#FFBE0B","#8338EC","#06D6A0",
    "#118AB2","#EF476F","#023E8A","#80B918","#F72585",
]

# ── Utilidades ───────────────────────────────────────────────
def dist_ruta(cantones):
    """Distancia total de un trip: CD → c1 → c2 → ... → CD"""
    if not cantones:
        return 0
    d = DISTANCIAS[0][cantones[0]]
    for k in range(len(cantones) - 1):
        d += DISTANCIAS[cantones[k]][cantones[k+1]]
    d += DISTANCIAS[cantones[-1]][0]
    return d

def duracion_min(trip):
    t_cond  = (trip["distancia"] / VEL_KMH) * 60
    t_par   = len(trip["cantones"]) * MIN_PARADA
    t_carga = trip["carga"] * MIN_PALLET
    return t_cond + t_par + t_carga

# ── Paso 1: Clarke-Wright savings ────────────────────────────
def clarke_wright():
    # Crear una subtarea por cada "carga" de un cantón
    # Cantón con demanda > 24 se divide en chunks de 24
    tareas = []
    for i in range(1, len(CANTONES)):
        dem = DEMANDA[i]
        while dem > 0:
            chunk = min(dem, CAPACIDAD)
            tareas.append({"cantones": [i], "carga": chunk})
            dem -= chunk

    # Savings s(i,j) = d(0,i) + d(0,j) - d(i,j)
    savings = []
    n = len(tareas)
    for a in range(n):
        for b in range(a+1, n):
            i = tareas[a]["cantones"][-1]
            j = tareas[b]["cantones"][0]
            s = DISTANCIAS[0][i] + DISTANCIAS[0][j] - DISTANCIAS[i][j]
            savings.append((s, a, b))
    savings.sort(reverse=True)

    merged = [False] * n
    for s, a, b in savings:
        if merged[a] or merged[b]:
            continue
        nueva_carga = tareas[a]["carga"] + tareas[b]["carga"]
        if nueva_carga > CAPACIDAD:
            continue
        nueva_ruta = tareas[a]["cantones"] + tareas[b]["cantones"]
        tareas[a] = {"cantones": nueva_ruta, "carga": nueva_carga}
        merged[b] = True

    trips = []
    for i, t in enumerate(tareas):
        if not merged[i]:
            d = dist_ruta(t["cantones"])
            trips.append({
                "cantones": t["cantones"],
                "carga":    t["carga"],
                "distancia": d,
                "ruta": [0] + t["cantones"] + [0],
            })
    return trips

# ── Paso 2: 2-opt por trip para MINIMIZAR distancia ─────────
def two_opt(cantones):
    """
    Mejora el orden de visita dentro de un trip
    intercambiando pares de arcos hasta que no haya mejora.
    Minimiza la distancia del trip.
    """
    if len(cantones) <= 2:
        return cantones, dist_ruta(cantones)

    mejor = cantones[:]
    mejor_dist = dist_ruta(mejor)
    mejorado = True

    while mejorado:
        mejorado = False
        for i in range(len(mejor)):
            for j in range(i+2, len(mejor)):
                nueva = mejor[:i+1] + mejor[i+1:j+1][::-1] + mejor[j+1:]
                nueva_dist = dist_ruta(nueva)
                if nueva_dist < mejor_dist - 0.01:
                    mejor = nueva
                    mejor_dist = nueva_dist
                    mejorado = True
    return mejor, mejor_dist

def optimizar_trips(trips):
    """Aplica 2-opt a cada trip para minimizar Z*"""
    optimizados = []
    for t in trips:
        cant_opt, dist_opt = two_opt(t["cantones"])
        optimizados.append({
            "cantones":  cant_opt,
            "carga":     t["carga"],
            "distancia": dist_opt,
            "ruta":      [0] + cant_opt + [0],
        })
    return optimizados

# ── Paso 3: bin-packing de trips en camiones (Hito 4) ────────
def asignar_camiones(trips):
    camiones = []
    for trip in sorted(trips, key=duracion_min, reverse=True):
        dur = duracion_min(trip)
        asignado = False
        for cam in camiones:
            usado = sum(duracion_min(t) for t in cam) + RECARGA_MIN * len(cam)
            if usado + dur <= JORNADA_MIN:
                cam.append(trip)
                asignado = True
                break
        if not asignado:
            camiones.append([trip])
    return camiones

# ── UI ───────────────────────────────────────────────────────
st.title("🍺 Florida Bebidas · Distribución Puntarenas")
st.caption("CVRP · Clarke-Wright + 2-opt · Minimización de distancia total · II-1122 · UCR Alajuela")

with st.sidebar:
    st.header("⚙️ Parámetros")
    resolver = st.button("▶ Resolver y Minimizar", type="primary", use_container_width=True)
    st.divider()
    st.markdown("**Algoritmo**")
    st.markdown("1. **Clarke-Wright** — construye rutas iniciales\n"
                "2. **2-opt** — minimiza distancia por trip\n"
                "3. **Bin-packing** — asigna trips a camiones (8h)")
    st.divider()
    st.markdown("**Provincia: Puntarenas**")
    st.metric("Cantones", 13)
    st.metric("Demanda total", "390 pallets/sem")
    st.metric("Capacidad camión", "24 pallets")
    st.metric("Jornada", "8 h / 480 min")
    st.metric("Velocidad", "40 km/h")

# Tabla demanda
st.subheader("📦 Demanda semanal por cantón")
df_dem = pd.DataFrame({
    "Cantón":        CANTONES[1:],
    "Imperial (p)":  [round(d*0.50) for d in DEMANDA[1:]],
    "Pilsen (p)":    [round(d*0.25) for d in DEMANDA[1:]],
    "Tropical (p)":  [round(d*0.25) for d in DEMANDA[1:]],
    "Total pallets": DEMANDA[1:],
})
st.dataframe(df_dem, use_container_width=True, hide_index=True)

if resolver:
    with st.spinner("Paso 1/3 — Construyendo rutas con Clarke-Wright..."):
        trips_iniciales = clarke_wright()
        dist_inicial = sum(t["distancia"] for t in trips_iniciales)

    with st.spinner("Paso 2/3 — Minimizando distancia con 2-opt..."):
        trips = optimizar_trips(trips_iniciales)
        dist_final = sum(t["distancia"] for t in trips)

    with st.spinner("Paso 3/3 — Asignando trips a camiones..."):
        camiones = asignar_camiones(trips)

    reduccion = dist_inicial - dist_final
    pct = (reduccion / dist_inicial * 100) if dist_inicial > 0 else 0

    # KPIs
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🗺️ Z* (distancia total)", f"{dist_final:.0f} km",
              delta=f"-{reduccion:.0f} km vs inicial", delta_color="inverse")
    c2.metric("📉 Reducción 2-opt", f"{pct:.1f}%")
    c3.metric("🚛 Trips", len(trips))
    c4.metric("🚚 Camiones físicos", len(camiones))

    # Comparación antes/después
    with st.expander("📊 Ver comparación antes y después de la minimización"):
        df_comp = pd.DataFrame({
            "Trip": list(range(1, len(trips)+1)),
            "Cantones": [" → ".join(CANTONES[n] for n in t["cantones"]) for t in trips_iniciales],
            "Dist. inicial (km)": [t["distancia"] for t in trips_iniciales],
            "Dist. minimizada (km)": [t["distancia"] for t in trips],
            "Ahorro (km)": [round(ti["distancia"] - tf["distancia"])
                            for ti, tf in zip(trips_iniciales, trips)],
        })
        st.dataframe(df_comp, use_container_width=True, hide_index=True)
        st.caption(f"Distancia inicial: {dist_inicial:.0f} km  →  "
                   f"Distancia minimizada (Z*): {dist_final:.0f} km  →  "
                   f"Ahorro total: {reduccion:.0f} km ({pct:.1f}%)")

    # Mapa
    st.subheader("🗺️ Mapa de rutas optimizadas")
    fig = go.Figure()
    for i, trip in enumerate(trips):
        color = COLORES[i % len(COLORES)]
        lats, lons, hover = [], [], []
        for n in trip["ruta"]:
            lat, lon = COORDS[CANTONES[n]]
            lats.append(lat); lons.append(lon)
            hover.append(CANTONES[n])
        fig.add_trace(go.Scattermapbox(
            lat=lats, lon=lons, mode="lines+markers",
            line=dict(width=2.5, color=color),
            marker=dict(size=9, color=color),
            name=f"Trip {i+1} · {trip['carga']}p · {trip['distancia']:.0f}km",
            hovertext=hover, hoverinfo="text",
        ))
    lat_cd, lon_cd = COORDS["CD Puntarenas"]
    fig.add_trace(go.Scattermapbox(
        lat=[lat_cd], lon=[lon_cd], mode="markers",
        marker=dict(size=20, color="white"),
        name="⭐ CD Puntarenas",
    ))
    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_zoom=7, mapbox_center={"lat":9.3,"lon":-83.8},
        margin=dict(l=0,r=0,t=0,b=0), height=530,
        legend=dict(font=dict(size=11)),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabla trips
    st.subheader("🚛 Detalle de trips — Hito 3")
    rows = []
    for i, t in enumerate(trips):
        ruta_str = " → ".join(CANTONES[n] for n in t["ruta"])
        rows.append({
            "Trip": i+1,
            "Ruta completa (minimizada)": ruta_str,
            "Pallets": t["carga"],
            "Distancia (km)": round(t["distancia"]),
            "Duración (min)": round(duracion_min(t)),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Tabla camiones
    st.subheader("🚚 Camiones físicos — Hito 4")
    rows_cam = []
    for i, cam in enumerate(camiones):
        tiempo = sum(duracion_min(t) for t in cam) + RECARGA_MIN*(len(cam)-1)
        rows_cam.append({
            "Camión": i+1,
            "Trips": ", ".join(f"T{trips.index(t)+1}" for t in cam),
            "Pallets totales": sum(t["carga"] for t in cam),
            "Km totales": round(sum(t["distancia"] for t in cam)),
            "Tiempo (min)": round(tiempo),
            "Tiempo (h)": round(tiempo/60, 1),
            "Estado": "⚠️ Dedicado" if tiempo > JORNADA_MIN else "✅ OK",
        })
    st.dataframe(pd.DataFrame(rows_cam), use_container_width=True, hide_index=True)

    # Pitch
    st.divider()
    st.subheader("💡 Resumen para el pitch — Hito 5")
    trip_largo = max(trips, key=lambda t: t["distancia"])
    ruta_largo = " → ".join(CANTONES[n] for n in trip_largo["ruta"])
    dedicados  = sum(1 for cam in camiones
                     if sum(duracion_min(t) for t in cam)+RECARGA_MIN*(len(cam)-1) > JORNADA_MIN)
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Provincia en una frase:** Puntarenas tiene 13 cantones, "
                f"390 pallets/semana y requiere **{len(camiones)} camiones físicos**.")
        st.info(f"**Trip más largo:** {ruta_largo} — **{trip_largo['distancia']:.0f} km.** "
                f"Causa: cantones del sur muy alejados del CD (Golfito, Corredores, Pto. Jiménez).")
    with col2:
        st.warning(f"**Camiones dedicados:** {dedicados} superan las 8 h de jornada "
                   f"por distancia extrema al sur de la provincia.")
        st.success(f"**Z* = {dist_final:.0f} km** — Clarke-Wright + 2-opt. "
                   f"Reducción lograda: {reduccion:.0f} km ({pct:.1f}%). "
                   f"Gap típico vs óptimo exacto: 1–5%.")

else:
    st.info("👈 Presiona **▶ Resolver y Minimizar** en el panel izquierdo.")
