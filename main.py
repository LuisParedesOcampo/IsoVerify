import streamlit as st
from pylinac import WinstonLutz
import tempfile
import os
import pandas as pd
import pydicom
import matplotlib.pyplot as plt
import warnings
from datetime import datetime
import io

# -------------------------------
# 1. CONFIGURACIÓN INICIAL
# -------------------------------
st.set_page_config(
    page_title="IsoVerify | Winston–Lutz QA",
    page_icon="🎯",
    layout="wide",
    menu_items={'About': "🎯 IsoVerify | Online Winston–Lutz QA Analyzer based on Pylinac"}
)

warnings.filterwarnings('ignore')

# -------------------------------
# 2. GESTIÓN DE ESTADO (MEMORIA)
# -------------------------------
if "analysis_complete" not in st.session_state:
    st.session_state.analysis_complete = False
if "wl_metrics" not in st.session_state:
    st.session_state.wl_metrics = {}
if "wl_figures" not in st.session_state:
    st.session_state.wl_figures = {}
if "pdf_data" not in st.session_state:
    st.session_state.pdf_data = None
if "df_trend" not in st.session_state:
    st.session_state.df_trend = None

st.title("🎯 IsoVerify : Winston-Lutz Analysis")
st.info("Online clinical tool for Winston Lutz calculations based on Pylinac")

# -------------------------------
# 3. BARRA LATERAL (INPUTS)
# -------------------------------
with st.sidebar:
    st.header("Analysis Parameters")
    tolerance = st.number_input("Tolerance (mm)", value=1.0, step=0.1)
    bb_size = st.number_input("BB Size (mm)", value=5.0, step=0.1)

    st.divider()
    st.header("📈 Trend Analysis")

    trend_mode = st.radio(
        "Trend Operation Mode",
        ["👁️ View existing trend", "🆕 Create new machine trend", "➕ Add result to trend"]
    )

    if trend_mode == "👁️ View existing trend":
        trend_csv = st.file_uploader("Upload trend CSV", type="csv")
        if trend_csv:
            st.session_state.df_trend = pd.read_csv(trend_csv)

    elif trend_mode == "🆕 Create new machine trend":
        st.markdown("**New Machine Setup**")
        machine_id = st.text_input("Machine ID (e.g. Linac1)")
        operator = st.text_input("Operator Initials")
        notes = st.text_input("Notes")

        if st.button("📄 Generate Trend File"):
            if st.session_state.analysis_complete:
                res = st.session_state.wl_metrics
                # USAMOS LA FECHA DEL DICOM, NO LA DE HOY
                dicom_date = res.get("date", datetime.now().strftime("%Y-%m-%d %H:%M"))

                new_row = {
                    "date": dicom_date,
                    "machine_id": machine_id,
                    "operator": operator,
                    "max_2d_mm": round(res["max_2d"], 3),
                    "gantry_iso_mm": round(res["gantry_3d"], 3),
                    "tolerance_mm": tolerance,
                    "pass_fail": "PASS" if res["max_2d"] <= tolerance else "FAIL",
                    "bb_size_mm": bb_size,
                    "n_images": res["n_images"],
                    "notes": notes
                }
                df_new = pd.DataFrame([new_row])
                st.session_state.df_trend = df_new

                st.success(f"Trend created with date: {dicom_date}")

                csv = df_new.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇️ Download CSV Now",
                    data=csv,
                    file_name=f"WL_Trend_{machine_id}.csv",
                    mime="text/csv",
                    key="sidebar_dl_new"
                )
            else:
                st.error("Run analysis first!")

    elif trend_mode == "➕ Add result to trend":
        trend_csv = st.file_uploader("Upload existing CSV", type="csv")
        operator = st.text_input("Operator")
        notes = st.text_input("Notes")

        if st.button("➕ Append Result"):
            if st.session_state.analysis_complete and trend_csv:
                try:
                    df_existing = pd.read_csv(trend_csv)
                    res = st.session_state.wl_metrics
                    # USAMOS LA FECHA DEL DICOM
                    dicom_date = res.get("date", datetime.now().strftime("%Y-%m-%d %H:%M"))

                    current_id = df_existing["machine_id"].iloc[0] if "machine_id" in df_existing.columns else "Unknown"

                    new_row = {
                        "date": dicom_date,
                        "machine_id": current_id,
                        "operator": operator,
                        "max_2d_mm": round(res["max_2d"], 3),
                        "gantry_iso_mm": round(res["gantry_3d"], 3),
                        "tolerance_mm": tolerance,
                        "pass_fail": "PASS" if res["max_2d"] <= tolerance else "FAIL",
                        "bb_size_mm": bb_size,
                        "n_images": res["n_images"],
                        "notes": notes
                    }
                    df_updated = pd.concat([df_existing, pd.DataFrame([new_row])], ignore_index=True)
                    # Ordenar por fecha para que la gráfica tenga sentido cronológico
                    df_updated['date_dt'] = pd.to_datetime(df_updated['date'])
                    df_updated = df_updated.sort_values(by='date_dt').drop(columns=['date_dt'])

                    st.session_state.df_trend = df_updated

                    st.success(f"Result added for date: {dicom_date}")

                    csv = df_updated.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="⬇️ Download Updated CSV",
                        data=csv,
                        file_name=f"WL_Trend_{current_id}.csv",
                        mime="text/csv",
                        key="sidebar_dl_append"
                    )

                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.error("Run analysis and upload CSV first!")

# -------------------------------
# 4. LÓGICA DE ANÁLISIS (PROTEGIDA)
# -------------------------------
uploaded_files = st.file_uploader("Upload DICOM files", accept_multiple_files=True, type=["dcm"])

if st.button("▶️ Run Winston–Lutz Analysis"):
    if uploaded_files:
        with st.spinner("Analyzing geometry..."):
            try:
                # 1. Extraer fecha del PRIMER archivo antes de procesar todo
                # Asumimos que todos los archivos son de la misma sesión
                first_file = uploaded_files[0]
                first_file.seek(0)
                ds_head = pydicom.dcmread(first_file, stop_before_pixels=True)

                # Intentamos buscar ContentDate (EPID) o AcquisitionDate
                date_tag = ds_head.get("ContentDate") or ds_head.get("AcquisitionDate") or ds_head.get(
                    "InstanceCreationDate")
                time_tag = ds_head.get("ContentTime") or ds_head.get("AcquisitionTime") or "120000"

                # Formatear fecha DICOM (YYYYMMDD) a legible (YYYY-MM-DD HH:MM)
                if date_tag:
                    try:
                        full_dt = datetime.strptime(f"{date_tag}{time_tag[:4]}", "%Y%m%d%H%M")
                        formatted_date = full_dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M")
                else:
                    formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M")

                # Resetear puntero del archivo para que Pylinac lo lea bien
                first_file.seek(0)

                with tempfile.TemporaryDirectory() as tmpdir:
                    for uploaded_file in uploaded_files:
                        uploaded_file.seek(0)
                        with open(os.path.join(tmpdir, uploaded_file.name), 'wb') as f:
                            f.write(uploaded_file.read())

                    wl = WinstonLutz(tmpdir)
                    wl.analyze(bb_size_mm=bb_size)

                    res = wl.results_data()

                    st.session_state.wl_metrics = {
                        "date": formatted_date,  # <--- AQUÍ GUARDAMOS LA FECHA REAL
                        "max_2d": res.max_2d_cax_to_bb_mm,
                        "gantry_3d": res.gantry_3d_iso_diameter_mm,
                        "n_images": len(wl.images),
                        "shift_instructions": wl.bb_shift_instructions()
                    }

                    plt.close('all')
                    wl.plot_summary()
                    fig_summary = plt.gcf()
                    st.session_state.wl_figures["summary"] = fig_summary

                    individual_figs = []
                    for img in wl.images:
                        fig, ax = plt.subplots()
                        img.plot(ax=ax)
                        ax.axis('off')
                        label = f"G={img.gantry_angle:.0f}° C={img.collimator_angle:.0f}° T={img.couch_angle:.0f}°"
                        individual_figs.append((label, fig))
                    st.session_state.wl_figures["individual"] = individual_figs

                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                        wl.publish_pdf(tmp_pdf.name, metadata={"Tolerance": f"{tolerance} mm"})
                        with open(tmp_pdf.name, "rb") as f:
                            st.session_state.pdf_data = f.read()

                    st.session_state.analysis_complete = True

            except Exception as e:
                st.error(f"Analysis Error: {e}")
                st.session_state.analysis_complete = False

# -------------------------------
# 5. VISUALIZACIÓN
# -------------------------------
if st.session_state.analysis_complete:
    metrics = st.session_state.wl_metrics

    st.divider()
    # Mostramos la fecha detectada para confirmación visual
    st.caption(f"📅 Image Acquisition Date: **{metrics.get('date', 'Unknown')}**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Max 2D Distance", f"{metrics['max_2d']:.3f} mm")
    c2.metric("Gantry Iso (Ø)", f"{metrics['gantry_3d']:.3f} mm")

    if metrics['max_2d'] <= tolerance:
        c3.success(f"✅ PASS (Tol: {tolerance}mm)")
    else:
        c3.error(f"❌ FAIL (Tol: {tolerance}mm)")

    st.info(f"**🛠 Couch Shift:** {metrics['shift_instructions']}")

    if st.session_state.pdf_data:
        st.download_button("⬇️ Download Report (PDF)", st.session_state.pdf_data, "WL_Report.pdf", "application/pdf")

    t1, t2 = st.tabs(["Isocenter Summary", "Individual Images"])

    with t1:
        if "summary" in st.session_state.wl_figures:
            st.pyplot(st.session_state.wl_figures["summary"])

    with t2:
        if "individual" in st.session_state.wl_figures:
            cols = st.columns(3)
            for i, (title, fig) in enumerate(st.session_state.wl_figures["individual"]):
                with cols[i % 3]:
                    st.caption(title)
                    st.pyplot(fig)

# -------------------------------
# 6. GRÁFICA DE TENDENCIAS
# -------------------------------
if st.session_state.df_trend is not None and not st.session_state.df_trend.empty:
    st.divider()
    st.subheader("📊 Historical Trend")

    df_chart = st.session_state.df_trend.copy()

    try:
        df_chart['date'] = pd.to_datetime(df_chart['date'])
        # Ordenamos por fecha para que la línea no haga zig-zag si subes datos antiguos
        df_chart = df_chart.sort_values(by='date')

        machine_label = df_chart['machine_id'].iloc[0] if 'machine_id' in df_chart.columns else "Unknown"

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(df_chart['date'], df_chart['max_2d_mm'], marker='o', linestyle='-')
        ax.axhline(y=tolerance, color='r', linestyle='--')
        ax.set_title(f"Stability: {machine_label}")
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

    except Exception as e:
        st.error(f"Error plotting trend: {e}")

# -------------------------------
# FOOTER / LEGAL
# -------------------------------
# Legal Disclaimer Section

st.divider()
st.subheader("⚠️ Disclaimer & Terms of Use")

st.markdown("""
<div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6;">
    <p style="color: #6c757d; font-size: 0.9em;">
        <strong>Notice:</strong> This software is intended for <strong>educational and research purposes only</strong>. 
        It is not a medical device and has not been cleared by any regulatory body (FDA, CE, etc.) for clinical use.
    </p>
    <ul style="color: #6c757d; font-size: 0.85em;">
        <li><strong>Responsibility:</strong> The user assumes all responsibility for the interpretation and clinical application of the results provided by this tool.</li>
        <li><strong>Verification:</strong> Calculations must be independently verified by a certified Medical Physicist before any clinical decision.</li>
        <li><strong>Liability:</strong> The developers of IsoVerify shall not be held liable for any damages, clinical errors, or consequences arising from the use or misuse of this software.</li>
    </ul>
    <p style="color: #6c757d; font-size: 0.85em; font-style: italic;">
        By using this application, you acknowledge and agree to these terms.
    </p>
</div>
""", unsafe_allow_html=True)
# Contact & Collaboration Section
st.write("")  # Espacio en blanco
st.subheader("Contact & Feedback")
st.markdown("""
Are you interested in new features or have suggestions for future developments? 
I am open to collaborations and professional opportunities in Medical Physics and Software Development.

- **LinkedIn:** [Luis Fernando Paredes ](https://www.linkedin.com/in/lfparedes1/)
- **GitHub:** [Project Repository](https://github.com/LuisParedesOcampo/IsoVerify)
- **Email:** luisfernandoparedes2@gmail.com

*Developed by a Clinical Medical Physicist*
""")