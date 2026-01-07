import re
from io import BytesIO
from datetime import date
import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Renegociaciones",
    layout="wide",
    initial_sidebar_state="collapsed", 
)

# --- ESTILOS CSS ---
st.markdown("""
<style>
    .config-box {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        margin-bottom: 20px;
    }
    .result-card {
        background-color: #ffffff;
        padding: 25px;
        border-radius: 12px;
        border-top: 5px solid #2e7d32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-top: 20px;
    }
    .stNumberInput input { font-weight: bold; }
    /* Ajuste tabla */
    [data-testid="stDataFrame"] { width: 100%; }
</style>
""", unsafe_allow_html=True)

# --- FUNCIONES DE AYUDA ---

def clp(n):
    try: 
        v = float(n)
        return "$ {:,.0f}".format(v).replace(",", ".")
    except: return "$ 0"

def _normalize_rut(x) -> str:
    if pd.isna(x): return ""
    t = re.sub(r"[^0-9kK]", "", str(x)).upper()
    if not t: return ""
    if len(t) > 1: return f"{int(t[:-1])}-{t[-1]}"
    return t

def _format_rut_visual(rut_std: str) -> str:
    if not rut_std or "-" not in rut_std: return rut_std
    try:
        cuerpo, dv = rut_std.split("-")
        cuerpo_fmt = "{:,}".format(int(cuerpo)).replace(",", ".")
        return f"{cuerpo_fmt}-{dv}"
    except: return rut_std

def _distribuir_redondeo(val_total: float, n: int):
    if n <= 0: return [0]
    base = int(round(val_total / n))
    partes = [base] * n
    diff = int(round(val_total)) - sum(partes)
    if partes: partes[-1] += diff
    return partes

def _generar_fechas(primer_pago: pd.Timestamp, n: int, periodicidad: str):
    """
    Genera N fechas partiendo EXACTAMENTE del primer_pago.
    Ej: Si primer_pago es 03-Nov, la lista empieza con 03-Nov.
    """
    fechas = []
    cur = pd.to_datetime(primer_pago)
    for _ in range(n):
        fechas.append(cur)
        if periodicidad == "Quincenal": 
            cur = cur + pd.Timedelta(days=15)
        else: 
            # Sumar un mes calendario
            cur = cur + relativedelta(months=1)
    return pd.DatetimeIndex(fechas)

def load_data_simple(uploaded_files):
    if not uploaded_files: return pd.DataFrame()
    df_list = []
    for file in uploaded_files:
        try:
            if file.name.endswith('.csv'):
                df_temp = pd.read_csv(file, sep=";", encoding="latin-1", on_bad_lines='skip')
            else:
                df_temp = pd.read_excel(file)
            df_temp.columns = df_temp.columns.str.strip()
            df_list.append(df_temp)
        except Exception as e: st.error(f"Error leyendo {file.name}: {e}")
    if df_list: return pd.concat(df_list, ignore_index=True)
    return pd.DataFrame()

# ==========================================
# UI CENTRALIZADA
# ==========================================

st.title("📂 Sistema de Renegociaciones")

# 1. CARGA
st.markdown("### 1. Carga de Datos")
uploaded_files = st.file_uploader("Sube tu Excel o CSV aquí", type=["xlsx", "xls", "csv"], accept_multiple_files=True)

df = pd.DataFrame()
if uploaded_files:
    if "df_cache" not in st.session_state:
        st.session_state["df_cache"] = load_data_simple(uploaded_files)
    df = st.session_state["df_cache"]
    
    rut_col_name = None
    for c in df.columns:
        if "rut" in c.lower():
            rut_col_name = c; break
    
    if rut_col_name:
        df.rename(columns={rut_col_name: "RUT"}, inplace=True)
        df["RUT_norm"] = df["RUT"].apply(_normalize_rut)
        st.success(f"✅ Datos cargados correctamente: {len(df):,} registros.")
    else:
        st.error("⚠️ No se encontró columna RUT."); st.stop()

# 2. CONFIGURACIÓN Y BÚSQUEDA
if not df.empty:
    st.markdown("### 2. Configuración y Búsqueda")
    
    with st.container(border=True):
        # FILA 1
        c1, c2, c3, c4 = st.columns(4)
        with c1: 
            # CORRECCIÓN: Etiqueta clara indicando que esta fecha es el Primer Pago
            fecha_calculo = st.date_input("Fecha Cálculo / 1er Pago", value=date.today())
        with c2: 
            tasa_mensual = st.number_input("Tasa Mensual (%)", value=0.33, step=0.01)
        with c3: 
            n_cuotas = st.number_input("N° Cuotas", min_value=1, value=1, step=1)
        with c4: 
            periodicidad = st.selectbox("Periodicidad", ["Mensual", "Quincenal"])
        
        # FILA 2 (Costos)
        with st.expander("b. Costos Asociados (Opcional)", expanded=False):
            cc1, cc2, cc3, cc4 = st.columns(4)
            with cc1: costo_jud = st.number_input("Costas judiciales", min_value=0, value=0)
            with cc2: honor_abog = st.number_input("Honorarios abogados", min_value=0, value=0)
            with cc3: g_cobranza = st.number_input("Gastos cobranza", min_value=0, value=0)
            with cc4: otros_cost = st.number_input("Otros gastos", min_value=0, value=0)
            
        costos_total_extras = float(costo_jud + honor_abog + g_cobranza + otros_cost)
        st.markdown("---")
        
        # FILA 3 (Buscador)
        c_search, c_btn = st.columns([3, 1])
        with c_search:
            rut_input = st.text_input("Ingresa RUT del Cliente", placeholder="Ej: 12345678")
        with c_btn:
            st.write(""); st.write("")
            btn_calcular = st.button("🔍 Calcular Ficha", type="primary", use_container_width=True)

    # --- LÓGICA DE CÁLCULO ---
    if btn_calcular and rut_input:
        rut_clean = _normalize_rut(rut_input)
        df_cliente = df[df["RUT_norm"] == rut_clean].copy()
        
        if df_cliente.empty:
            st.warning(f"No se encontró información para el RUT: {_format_rut_visual(rut_clean)}")
        else:
            try:
                # --- CÁLCULO PARTE 1 ---
                nombre = df_cliente.iloc[0].get("Nombre cliente", "Cliente Sin Nombre")
                cia = df_cliente.iloc[0].get("Compañía", "Sin Compañía")
                
                col_monto = "M. Pendiente" if "M. Pendiente" in df_cliente.columns else df_cliente.columns[0]
                col_vcto = "F. Vcto." if "F. Vcto." in df_cliente.columns else None

                df_cliente["Monto Base"] = pd.to_numeric(df_cliente[col_monto], errors='coerce').fillna(0)
                
                if col_vcto:
                    df_cliente["Fecha Ref"] = pd.to_datetime(df_cliente[col_vcto], dayfirst=True, errors='coerce')
                    # Días de atraso hasta la fecha de cálculo
                    df_cliente["Días Atraso"] = (pd.to_datetime(fecha_calculo) - df_cliente["Fecha Ref"]).dt.days.clip(lower=0).fillna(0).astype(int)
                else:
                    df_cliente["Días Atraso"] = 0

                factor_diario = (tasa_mensual / 100) / 30
                df_cliente["Interés Calculado"] = (df_cliente["Monto Base"] * factor_diario * df_cliente["Días Atraso"]).round(0)
                df_cliente["IVA Interés"] = (df_cliente["Interés Calculado"] * 0.19).round(0)
                df_cliente["Total Interés"] = df_cliente["Interés Calculado"] + df_cliente["IVA Interés"]
                
                total_capital_p1 = df_cliente["Monto Base"].sum()
                total_interes_p1 = df_cliente["Total Interés"].sum()
                deuda_total_p1 = total_capital_p1 + total_interes_p1
                rut_bonito = _format_rut_visual(rut_clean)

                # TARJETA PARTE 1
                st.markdown(f"""
                <div class="result-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #eee; padding-bottom:10px; margin-bottom:15px;">
                        <h2 style="margin:0; color:#333;">👤 {nombre}</h2>
                        <span style="color:#777;">Fecha Cálculo: {fecha_calculo.strftime('%d-%m-%Y')}</span>
                    </div>
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:20px;">
                        <div><small style="color:#888; font-weight:bold;">RUT</small><br><span style="font-size:1.2rem; font-weight:600;">{rut_bonito}</span></div>
                        <div><small style="color:#888; font-weight:bold;">COMPAÑÍA</small><br><span style="font-size:1.1rem;">{cia}</span></div>
                        <div><small style="color:#888; font-weight:bold;">CAPITAL ABIERTO</small><br><span style="font-size:1.2rem; color:#d63384;">{clp(total_capital_p1)}</span></div>
                        <div><small style="color:#888; font-weight:bold;">INTERESES + IVA</small><br><span style="font-size:1.2rem; color:#fd7e14;">{clp(total_interes_p1)}</span></div>
                        <div style="background:#e8f5e9; padding:10px; border-radius:8px; border:1px solid #c8e6c9; text-align:center;">
                            <small style="color:#2e7d32; font-weight:bold;">DEUDA TOTAL A PAGAR</small><br>
                            <span style="font-size:1.4rem; font-weight:bold; color:#1b5e20;">{clp(deuda_total_p1)}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("Ver Detalle de Documentos", expanded=False):
                    st.dataframe(df_cliente, use_container_width=True)

                # ==========================================
                # PARTE 2: PLAN DE CUOTAS
                # ==========================================
                st.markdown("### 📅 Plan de Pagos Propuesto (Parte 2)")
                
                if n_cuotas > 0:
                    N = int(n_cuotas)
                    tasa_m = tasa_mensual / 100.0
                    iva_pct = 0.19
                    
                    saldo_deuda_total = int(round(deuda_total_p1))
                    capital_tot_reneg = int(round(total_capital_p1))
                    
                    # 1. Capital igualitario
                    capital_cuotas = _distribuir_redondeo(capital_tot_reneg, N)
                    
                    # 2. Fechas de pago (CORRECCIÓN: Empieza en fecha_calculo)
                    fechas_pago = _generar_fechas(pd.to_datetime(fecha_calculo), N, periodicidad)
                    
                    # 3. Fechas para cálculo de DÍAS (Exactas)
                    if periodicidad == "Mensual":
                        fecha_posterior = fechas_pago[-1] + relativedelta(months=1)
                    else:
                        fecha_posterior = fechas_pago[-1] + pd.Timedelta(days=15)
                    
                    fechas_referencia = list(fechas_pago) + [fecha_posterior]
                    
                    dias_lista = []
                    for i in range(N):
                        # Cálculo de días para intereses de ESTA cuota hacia la SIGUIENTE
                        delta = fechas_referencia[i+1] - fechas_referencia[i]
                        dias_reales = delta.days
                        
                        if i == N - 1: dias_reales = 0 # Última cuota sin proyección de días
                        dias_lista.append(dias_reales)

                    # 4. Bucle de cálculo
                    rows = []
                    costos_cuota_list = _distribuir_redondeo(costos_total_extras, N)
                    
                    for i in range(N):
                        cap_i = capital_cuotas[i]
                        dias_i = dias_lista[i]
                        costo_i = costos_cuota_list[i]
                        
                        # Saldo Inicio
                        if i == 0:
                            saldo_base = saldo_deuda_total
                        else:
                            saldo_base = rows[i-1]["Saldo inicio"] - rows[i-1]["Capital"]
                        
                        # Cálculo Intereses (Basado en días hacía la próxima fecha)
                        float_int_net = saldo_base * (tasa_m / 30.0) * dias_i
                        float_iva = float_int_net * iva_pct
                        
                        int_net = int(round(float_int_net))
                        iva_i = int(round(float_iva))
                        inte = int_net + iva_i
                        
                        if i == N - 1: 
                            int_net = 0; iva_i = 0; inte = 0
                        
                        cuota_total = cap_i + inte + costo_i
                        
                        rows.append({
                            "N°": i+1,
                            "Fecha de pago": fechas_pago[i].strftime("%d-%m-%Y"),
                            "Días": dias_i,
                            "Saldo inicio": saldo_base,
                            "Capital": cap_i,
                            "Interés neto": int_net,
                            "IVA": iva_i,
                            "Interés": inte,
                            "Costos": costo_i,
                            "Cuota": cuota_total
                        })
                    
                    df_plan = pd.DataFrame(rows)
                    
                    # Mostrar
                    c_res1, c_res2 = st.columns([3, 1])
                    with c_res1:
                        df_show = df_plan.copy()
                        for c in ["Saldo inicio", "Capital", "Interés neto", "IVA", "Interés", "Costos", "Cuota"]:
                            df_show[c] = df_show[c].apply(clp)
                        st.dataframe(df_show, use_container_width=True, hide_index=True)
                    
                    with c_res2:
                        total_plan = df_plan["Cuota"].sum()
                        st.info(f"**Total Plan:**\n\n{clp(total_plan)}")
                        
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            df_cliente.to_excel(writer, sheet_name='Detalle', index=False)
                            df_plan.to_excel(writer, sheet_name='Cuotas', index=False)
                        st.download_button("Descargar Excel", output.getvalue(), f"Plan_{rut_clean}.xlsx")
                
                else:
                    st.info("Aumenta el N° de Cuotas para ver el plan.")

            except Exception as e:
                st.error(f"Error: {e}")
                # st.exception(e) # Descomentar para debug
else:
    st.info("👋 Carga tu archivo para comenzar.")