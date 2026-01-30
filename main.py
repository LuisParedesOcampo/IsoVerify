import streamlit as st
from pylinac import WinstonLutz
import tempfile
import os
import pandas as pd
import pydicom
import matplotlib.pyplot as plt
import warnings

st.set_page_config(
    page_title="🎯 IsoVerify | Online Winston–Lutz QA Analyzer for SRS/SBRT based on Pylinac",
    page_icon="🎯",
    layout="wide",
    menu_items={
        'About':"🎯 IsoVerify | Online Winston–Lutz QA Analyzer for SRS/SBRT based on Pylinac"
    }
)
# Bloqueamos avisos internos para que no "ensucien" la interfaz web
warnings.filterwarnings('ignore')

# -------------------------------
# CONFIGURACIÓN DE PÁGINA
# -------------------------------
st.set_page_config(page_title="Winston-Lutz QA", layout="wide")
st.title("🎯 IsoVerify : Winston-Lutz Analysis")
st.info("Online clinical tool for Winston Lutz calculations based on Pylinac")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("Analysis Parameters")
    tolerance = st.number_input("Tolerance (mm)", value=1.0, step=0.1)
    st.info("Tolerance for SRS treatments is 1mm.")
    bb_size = st.number_input("BB Size (mm)", value=5.0, step=0.1)
    st.info("The PDF report will include details for each analyzed image.")

# --- CARGA DE ARCHIVOS ---
uploaded_files = st.file_uploader(
    "Upload DICOM files (.dcm)",
    accept_multiple_files=True,
    type=["dcm"]
)

if uploaded_files:
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_rows = []
        for uploaded_file in uploaded_files:
            file_data = uploaded_file.read()
            ds = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file_data))

            metadata_rows.append({
                "File": uploaded_file.name,
                "Gantry (°)": getattr(ds, "GantryAngle", 0.0),
                "Collimador (°)": getattr(ds, "BeamLimitingDeviceAngle", 0.0),
                "Couch (°)": getattr(ds, "PatientSupportAngle", 0.0)
            })

            with open(os.path.join(tmpdir, uploaded_file.name), 'wb') as f:
                f.write(file_data)

        # 🛠️ CORRECCIÓN: Usamos width="stretch" para cumplir con el estándar 2026
        st.subheader("📋 DICOM Metadata Inspection")
        st.dataframe(pd.DataFrame(metadata_rows), width="stretch")

        try:
            with st.spinner("Performing geometric analysis..."):
                wl = WinstonLutz(tmpdir)
                wl.analyze(bb_size_mm=bb_size)

            # -------------------------------
            # RESULTADOS Y MÉTRICAS
            # -------------------------------
            res = wl.results_data()
            st.divider()

            c1, c2, c3 = st.columns(3) #tres columnas para mostrar los resultados
            # Acceso directo a los atributos que ya verificamos que funcionan
            max_2d = res.max_2d_cax_to_bb_mm
            gantry_3d = res.gantry_3d_iso_diameter_mm

            c1.metric("Max 2D Distance (CAX → BB)", f"{max_2d:.3f} mm")
            c2.metric("Gantry Isocenter Diameter (Ø)", f"{gantry_3d:.3f} mm")

            if max_2d <= tolerance:
                c3.success(f"✅ PASS (Tol: {tolerance} mm)")
            else:
                c3.error(f"❌ FAIL (Tol: {tolerance} mm)")

            # Instrucción clínica destacada (Simula el shift del PDF)
            st.info(f"**🛠 Couch Shift Instruction:** {wl.bb_shift_instructions()}")

            st.warning(
                "⚠️ Couch shifts are reported in pylinac's internal geometric coordinate system. "
                "Please verify your machine coordinate convention (IEC 61217, vendor-specific) "
                "before applying clinical corrections."
            )

            # -------------------------------
            # REPORTE PDF
            # ------------------------------
            st.divider()
            st.subheader("📄 PDF Report")

            with st.spinner("Generating PDF report (this may take a few seconds)..."):
                with tempfile.NamedTemporaryFile(
                        suffix=".pdf",
                        delete=False
                ) as tmp_pdf:
                    pdf_path = tmp_pdf.name

                wl.publish_pdf(
                    pdf_path,
                    notes="PDF Generated from IsoVery",
                    metadata={
                        "Tolerance": f"{tolerance:.1f} mm"
                    }
                )

                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()

            st.success("✅ PDF report generated successfully")

            st.download_button(
                label="⬇️ Download Winston-Lutz Report (PDF)",
                data=pdf_bytes,
                file_name="Winston_Lutz_QA_Report.pdf",
                mime="application/pdf"
            )

            # -------------------------------
            st.divider()
            # -------------------------------
            # GRÁFICOS
            # -------------------------------
            tab1, tab2 = st.tabs(["Isocenter Summary", "Individual Image Detection"])

            with tab1:
                st.subheader("📊 Isocenter Summary")

                # Limpia cualquier figura previa
                plt.close("all")

                # Pylinac dibuja sobre pyplot
                wl.plot_summary()

                # Captura la figura ACTUAL creada por pylinac
                fig = plt.gcf()

                # Pásala explícitamente a Streamlit
                st.pyplot(fig)

                # Cierra para evitar fugas de estado
                plt.close(fig)

            from matplotlib.figure import Figure

            with tab2:
                st.subheader("📸 Individual Image Detection")

                for i, img in enumerate(wl.images, start=1):
                    st.markdown(
                        f"**Image {i}**  "
                        f"(G={img.gantry_angle:.0f}°, "
                        f"C={img.collimator_angle:.0f}°, "
                        f"T={img.couch_angle:.0f}°)"
                    )

                    plt.close("all")

                    fig = plt.figure(figsize=(1, 1), dpi=100)
                    img.plot()

                    fig = plt.gcf()

                    st.pyplot(fig,use_container_width=False)  # 🔴 ESTA LÍNEA ES LA CLAVE

                    plt.close(fig)



        except Exception as e:
            st.error("Error in Winston-Lutz analysis.")
            st.exception(e)
else:
    st.info("Waiting for DICOM files...")
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
