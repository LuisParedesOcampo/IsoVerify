# IsoVerify

🚀 **Live App Access:** [https://isoverify.streamlit.app/]

**IsoVerify** is an open-source, web-based clinical QA tool for  
**Winston–Lutz isocenter verification** in radiotherapy.

A web-based clinical Quality Assurance (QA) tool for **Winston–Lutz analysis** in stereotactic radiotherapy and radiosurgery.

This application is built using **Streamlit** and **pylinac**, allowing medical physicists to:
- Analyze Winston–Lutz DICOM image sets
- Visualize isocenter accuracy
- Generate official pylinac PDF reports
- Inspect individual image detections interactively

---

## 🚀 Features

- 📂 Upload multiple DICOM EPID images
- 📊 Automatic Winston–Lutz geometric analysis
- 🎯 Gantry isocenter diameter and max CAX–BB distance
- 🛠 Couch shift vector calculation (with coordinate system warning)
- 📸 Individual image visualization
- 📄 One-click PDF report generation (pylinac official report)
- 🌐 Web-based UI (Streamlit)

---

## ⚠️ Clinical Disclaimer

This tool performs **geometric analysis only**.

Couch shift values are reported in **pylinac’s internal geometric coordinate system**.  
Before applying any clinical correction, users **must verify** their machine’s coordinate convention (e.g. IEC 61217, vendor-specific).

This software does **not replace clinical judgment**.

---

## 🖥️ Installation

### 1. Clone the repository

```bash
git clone 
cd winston-lutz-streamlit
