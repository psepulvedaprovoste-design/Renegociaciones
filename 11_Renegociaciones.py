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
    .total-box {
        background-color: #e8f5e9;
        padding: 15px;
        border-radius: 8px;
        margin-top: 20px;
        border: 2px solid #c8e6c9;
    }
    .stNumberInput input { font-weight: bold; }
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
    fechas = []
    cur = pd.to_datetime(primer_pago)
    for _ in range(n):
        fechas.append(cur)
        if periodicidad == "Quincenal": 
            cur = cur + pd.Timedelta(days=15)
        else: 
            cur = cur + relativedelta(months=1)
    return pd.DatetimeIndex(fechas)

def load_data_simple(uploaded_files):
    if not uploaded_files: return pd.DataFrame()
    df_list = []
    for file in uploaded_files:
        try:
            if file.name.endswith('.csv'):
                try:
                    df_temp = pd.read_csv(file, sep=";", encoding="latin-1", on_bad_lines='skip')
                    if len(df_temp.columns) < 2: 
                         file.seek(0)
                         df_temp = pd.read_csv(file, sep=",", encoding="latin-1", on_bad_lines='skip')
                except:
                    file.seek(0)
                    df_temp = pd.read_csv(file, sep=",", encoding="latin-1", on_bad_lines='skip')
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
    possible_rut_cols = ["RUT", "Rut", "rut", "Tax ID", "Identificador"]
    for cand in possible_rut_cols:
        if cand in df.columns:
            rut_col_name = cand; break
    if not rut_col_name:
        for c in df.columns:
            if "rut" in c.lower(): rut_col_name = c; break
    
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
        c1, c2, c3, c4 = st.columns(4)
        with c1: fecha_calculo = st.date_input("Fecha Cálculo / 1er Pago", value=date.today())
        with c2: tasa_mensual = st.number_input("Tasa Mensual (%)", value=0.33, step=0.01)
        with c3: n_cuotas = st.number_input("N° Cuotas", min_value=1, value=1, step=1)
        with c4: periodicidad = st.selectbox("Periodicidad", ["Mensual", "Quincenal"])
        
        with st.expander("b. Costos Asociados y Honorarios", expanded=True):
            cc1, cc2, cc3, cc4 = st.columns(4)
            with cc1: costo_jud = st.number_input("Costas judiciales", min_value=0, value=0)
            with cc2: honor_abog = st.number_input("Honorarios abogados", min_value=0, value=0)
            with cc3: g_cobranza = st.number_input("Gastos cobranza", min_value=0, value=0)
            with cc4: otros_cost = st.number_input("Otros gastos", min_value=0, value=0)
            
        costos_total_extras = float(costo_jud + honor_abog + g_cobranza + otros_cost)
        st.markdown("---")
        
        c_search, c_btn = st.columns([3, 1])
        with c_search:
            rut_input = st.text_input("Ingresa RUT del Cliente", placeholder="Ej: 12345678")
        with c_btn:
            st.write(""); st.write("")
            btn_calcular = st.button("🔍 Calcular Ficha", type="primary", use_container_width=True)

    # --- MANEJO DE ESTADO PARA PERSISTENCIA ---
    if "calc_done" not in st.session_state:
        st.session_state["calc_done"] = False
    if "rut_target" not in st.session_state:
        st.session_state["rut_target"] = ""

    if btn_calcular and rut_input:
        st.session_state["calc_done"] = True
        st.session_state["rut_target"] = rut_input

    # --- LÓGICA DE CÁLCULO ---
    if st.session_state["calc_done"] and st.session_state["rut_target"]:
        rut_clean = _normalize_rut(st.session_state["rut_target"])
        df_cliente = df[df["RUT_norm"] == rut_clean].copy()
        
        if df_cliente.empty:
            st.warning(f"No se encontró información para el RUT: {_format_rut_visual(rut_clean)}")
        else:
            try:
                # --- CALCULO PARTE 1 ---
                nombre = "Cliente Sin Nombre"
                cols_nombre = [c for c in df_cliente.columns if "alpha name" in c.lower() or "nombre" in c.lower() or "cliente" in c.lower()]
                if cols_nombre: nombre = df_cliente.iloc[0][cols_nombre[0]]

                cia = "Sin Compañía"
                cols_cia = [c for c in df_cliente.columns if "compañ" in c.lower() or "company" in c.lower() or "document com" in c.lower()]
                if cols_cia: cia = df_cliente.iloc[0][cols_cia[0]]
                
                # Monto
                col_monto = None
                prioridades_monto = ["Open Amount", "M. Pendiente", "Saldo", "Deuda", "Monto", "Gross Amount"]
                for p in prioridades_monto:
                    match = next((c for c in df_cliente.columns if p.lower() == c.lower()), None)
                    if match: col_monto = match; break
                if not col_monto:
                    nums = df_cliente.select_dtypes(include=['float', 'int']).columns
                    col_monto = nums[-1] if len(nums) > 0 else df_cliente.columns[0]

                # Fecha Vcto
                col_vcto = None
                prioridades_fecha = ["Due Date", "F. Vcto.", "Vencimiento", "Date"]
                for p in prioridades_fecha:
                    match = next((c for c in df_cliente.columns if p.lower() in c.lower()), None)
                    if match: col_vcto = match; break

                # Tipo Doc y Numero
                col_tipo = next((c for c in df_cliente.columns if "tipo" in c.lower() or "type" in c.lower()), None)
                col_num = next((c for c in df_cliente.columns if "número" in c.lower() or "doc" in c.lower() or "number" in c.lower()), None)

                # Cálculos P1
                df_cliente["Monto Base"] = pd.to_numeric(df_cliente[col_monto], errors='coerce').fillna(0)
                
                if col_vcto:
                    df_cliente["Fecha Ref"] = pd.to_datetime(df_cliente[col_vcto], dayfirst=True, errors='coerce')
                    df_cliente["Días Atraso"] = (pd.to_datetime(fecha_calculo) - df_cliente["Fecha Ref"]).dt.days.clip(lower=0).fillna(0).astype(int)
                else:
                    df_cliente["Días Atraso"] = 0

                factor_diario = (tasa_mensual / 100) / 30
                df_cliente["Interés Neto"] = (df_cliente["Monto Base"] * factor_diario * df_cliente["Días Atraso"]).round(0)
                df_cliente["IVA Interés"] = (df_cliente["Interés Neto"] * 0.19).round(0)
                df_cliente["Total Interés"] = df_cliente["Interés Neto"] + df_cliente["IVA Interés"]
                
                total_capital_p1 = df_cliente["Monto Base"].sum()
                total_interes_p1 = df_cliente["Total Interés"].sum()
                deuda_total_p1 = total_capital_p1 + total_interes_p1
                rut_bonito = _format_rut_visual(rut_clean)

                # --- VISUALIZACIÓN FICHA ---
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
                            <small style="color:#2e7d32; font-weight:bold;">DEUDA TOTAL (CAPITAL + INTERÉS)</small><br>
                            <span style="font-size:1.4rem; font-weight:bold; color:#1b5e20;">{clp(deuda_total_p1)}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # --- PREPARACIÓN DATOS PARA TABLA Y EXCEL ---
                # Creamos un DF limpio con solo las columnas que se ven
                tabla_detalle_export = pd.DataFrame()
                tabla_detalle_export["Tipo Documento"] = df_cliente[col_tipo] if col_tipo else "N/A"
                tabla_detalle_export["Número Documento"] = df_cliente[col_num] if col_num else "N/A"
                tabla_detalle_export["Monto ($)"] = df_cliente["Monto Base"] # Numérico para Excel
                tabla_detalle_export["Fecha Venc."] = df_cliente["Fecha Ref"].dt.strftime('%d-%m-%Y') if col_vcto else "N/A"
                tabla_detalle_export["Fecha Cálculo"] = fecha_calculo.strftime('%d-%m-%Y')
                tabla_detalle_export["Días Plazo"] = df_cliente["Días Atraso"]
                tabla_detalle_export["Interés Neto"] = df_cliente["Interés Neto"] # Numérico
                tabla_detalle_export["I.V.A."] = df_cliente["IVA Interés"] # Numérico
                tabla_detalle_export["Total Intereses"] = df_cliente["Total Interés"] # Numérico

                # Versión visual (strings con $)
                tabla_detalle_visual = tabla_detalle_export.copy()
                for col in ["Monto ($)", "Interés Neto", "I.V.A.", "Total Intereses"]:
                    tabla_detalle_visual[col] = tabla_detalle_visual[col].apply(clp)

                # --- TABLA DETALLE VISUAL ---
                with st.expander("Ver Detalle de Documentos", expanded=False):
                    st.dataframe(tabla_detalle_visual, use_container_width=True, hide_index=True)

                # --- PARTE 2: PLAN DE CUOTAS ---
                st.markdown("### 📅 Plan de Pagos Propuesto (Parte 2)")
                
                if n_cuotas > 0:
                    N = int(n_cuotas)
                    tasa_m = tasa_mensual / 100.0
                    iva_pct = 0.19
                    
                    saldo_deuda_total = int(round(deuda_total_p1))
                    capital_tot_reneg = int(round(total_capital_p1))
                    
                    capital_cuotas = _distribuir_redondeo(capital_tot_reneg, N)
                    fechas_pago = _generar_fechas(pd.to_datetime(fecha_calculo), N, periodicidad)
                    
                    if periodicidad == "Mensual":
                        fecha_posterior = fechas_pago[-1] + relativedelta(months=1)
                    else:
                        fecha_posterior = fechas_pago[-1] + pd.Timedelta(days=15)
                    
                    fechas_referencia = list(fechas_pago) + [fecha_posterior]
                    
                    lista_intereses = []
                    temp_saldo = saldo_deuda_total
                    temp_interes_previo = 0
                    
                    for i in range(N):
                        delta = fechas_referencia[i+1] - fechas_referencia[i]
                        dias_r = delta.days
                        if i == N - 1: dias_r = 0
                        cap = capital_cuotas[i]
                        base_calculo = temp_saldo - cap + temp_interes_previo
                        int_net = int(round(base_calculo * (tasa_m / 30.0) * dias_r))
                        iva_i = int(round(int_net * iva_pct))
                        total_int_i = int_net + iva_i
                        if i == N - 1: total_int_i = 0 
                        lista_intereses.append(total_int_i)
                        temp_saldo = base_calculo
                        temp_interes_previo = total_int_i
                        
                    total_new_interests = sum(lista_intereses)
                    total_cuotas_pura = saldo_deuda_total + total_new_interests
                    cuota_fija = int(round(total_cuotas_pura / N))
                    
                    rows = []
                    current_saldo = saldo_deuda_total
                    prev_interest = 0
                    costos_cuota_list = _distribuir_redondeo(costos_total_extras, N)
                    
                    for i in range(N):
                        cap_i = capital_cuotas[i]
                        int_i = lista_intereses[i]
                        costo_i = costos_cuota_list[i]
                        dias_i = (fechas_referencia[i+1] - fechas_referencia[i]).days
                        if i == N - 1: dias_i = 0
                        
                        saldo_tabla = current_saldo - cap_i + prev_interest
                        neto_show = int(round(int_i / 1.19)) if int_i > 0 else 0
                        iva_show = int_i - neto_show

                        rows.append({
                            "N°": i+1,
                            "Fecha de pago": fechas_pago[i].strftime("%d-%m-%Y"),
                            "Días": dias_i,
                            "Saldo Deuda": saldo_tabla,
                            "Capital": cap_i,
                            "Interés neto": neto_show,
                            "IVA": iva_show,
                            "Interés": int_i,
                            "Costos": costo_i,
                            "Cuota (Cap+Int)": cuota_fija 
                        })
                        current_saldo = saldo_tabla
                        prev_interest = int_i
                    
                    df_plan = pd.DataFrame(rows)
                    
                    # --- MOSTRAR RESULTADOS FINALES ---
                    c_res1, c_res2 = st.columns([2, 1])
                    with c_res1:
                        df_show = df_plan.copy()
                        for c in ["Saldo Deuda", "Capital", "Interés neto", "IVA", "Interés", "Costos", "Cuota (Cap+Int)"]:
                            df_show[c] = df_show[c].apply(clp)
                        st.dataframe(df_show, use_container_width=True, hide_index=True)
                    
                    with c_res2:
                        total_cuotas_calc = df_plan["Cuota (Cap+Int)"].sum()
                        gran_total_final = total_cuotas_calc + costos_total_extras
                        
                        st.markdown(f"""
                        <div style="background:#f8f9fa; padding:15px; border-radius:10px; border:1px solid #ddd;">
                            <h4 style="margin-top:0;">💰 Resumen Final</h4>
                            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                                <span>Total Cuotas (Cap + Int):</span>
                                <strong>{clp(total_cuotas_calc)}</strong>
                            </div>
                            <hr style="margin:5px 0;">
                            <div style="display:flex; justify-content:space-between; margin-bottom:5px; color:#666;">
                                <span>+ Costas Judiciales:</span>
                                <span>{clp(costo_jud)}</span>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-bottom:5px; color:#666;">
                                <span>+ Honorarios Abogados:</span>
                                <span>{clp(honor_abog)}</span>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-bottom:5px; color:#666;">
                                <span>+ Gastos Cobranza:</span>
                                <span>{clp(g_cobranza)}</span>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-bottom:5px; color:#666;">
                                <span>+ Otros:</span>
                                <span>{clp(otros_cost)}</span>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-top:10px; padding-top:10px; border-top:2px solid #333; font-size:1.2em; color:#2e7d32;">
                                <strong>TOTAL FINAL A PAGAR:</strong>
                                <strong>{clp(gran_total_final)}</strong>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # --- GENERACIÓN DE EXCEL AVANZADO ---
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            workbook = writer.book
                            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#2e7d32', 'font_color': 'white', 'border': 1, 'align': 'center'})
                            fmt_money = workbook.add_format({'num_format': '$ #,##0', 'border': 1})
                            fmt_normal = workbook.add_format({'border': 1, 'align': 'center'})
                            fmt_bold = workbook.add_format({'bold': True})
                            
                            # --- HOJA 1: PLAN DE PAGOS ---
                            sheet = workbook.add_worksheet("Plan de Pagos")
                            writer.sheets["Plan de Pagos"] = sheet
                            sheet.write(0, 0, f"PLAN DE PAGOS: {nombre}", fmt_bold)
                            sheet.write(1, 0, f"RUT: {rut_clean} | Fecha: {fecha_calculo}", fmt_bold)
                            
                            cols = df_plan.columns.tolist()
                            for col_num, val in enumerate(cols):
                                sheet.write(3, col_num, val, fmt_header)
                            
                            for r_idx, row in enumerate(df_plan.values):
                                for c_idx, val in enumerate(row):
                                    if c_idx in [3, 4, 5, 6, 7, 8, 9]: # Money cols
                                        sheet.write(4 + r_idx, c_idx, val, fmt_money)
                                    else:
                                        sheet.write(4 + r_idx, c_idx, val, fmt_normal)
                                        
                            start_resumen = 4 + len(df_plan) + 2
                            sheet.write(start_resumen, 0, "RESUMEN FINAL", fmt_header)
                            sheet.write(start_resumen, 1, "MONTO", fmt_header)
                            resumen_items = [
                                ("Total Cuotas", total_cuotas_calc),
                                ("Costas Judiciales", costo_jud),
                                ("Honorarios Abogados", honor_abog),
                                ("Gastos Cobranza", g_cobranza),
                                ("Otros Gastos", otros_cost),
                                ("TOTAL FINAL A PAGAR", gran_total_final)
                            ]
                            for i, (label, val) in enumerate(resumen_items):
                                sheet.write(start_resumen + 1 + i, 0, label, fmt_normal)
                                sheet.write(start_resumen + 1 + i, 1, val, fmt_money)
                            sheet.set_column('A:Z', 18)
                            
                            # --- HOJA 2: DETALLE DOCUMENTOS (FORMATO LIMPIO) ---
                            sheet2 = workbook.add_worksheet("Detalle Documentos")
                            writer.sheets["Detalle Documentos"] = sheet2
                            
                            sheet2.write(0, 0, "DETALLE DE DOCUMENTOS (PARTE 1)", fmt_bold)
                            
                            cols_det = tabla_detalle_export.columns.tolist()
                            for col_num, val in enumerate(cols_det):
                                sheet2.write(2, col_num, val, fmt_header)
                            
                            for r_idx, row in enumerate(tabla_detalle_export.values):
                                for c_idx, val in enumerate(row):
                                    # Indices Money: Monto(2), Neto(6), IVA(7), Total(8)
                                    if c_idx in [2, 6, 7, 8]:
                                        sheet2.write(3 + r_idx, c_idx, val, fmt_money)
                                    else:
                                        sheet2.write(3 + r_idx, c_idx, val, fmt_normal)
                            
                            sheet2.set_column('A:Z', 20)
                            
                        st.download_button("📥 Descargar Plan (Excel)", output.getvalue(), f"Plan_{rut_clean}.xlsx", use_container_width=True)
                else:
                    st.info("Aumenta el N° de Cuotas para ver el plan.")

            except Exception as e:
                st.error(f"Error: {e}")
else:
    st.info("👋 Carga tu archivo para comenzar.")