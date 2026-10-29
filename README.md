# CBCT TMJ Analysis

A 3D Slicer Scripted Module for temporomandibular joint (TMJ) analysis on paired T1/T2 CBCT images and masks. The workflow separates registration from anatomical analysis and visualization.

> **Status:** Research software. Validate image geometry, transform direction, and displacement-field semantics on your own data before interpreting measurements. This repository is not a medical device and is not intended for clinical decision-making.

## Main workflow

1. **Registration (external Python):** ANTsPy SyNAggro registration, sphenoid-based Kabsch rigid fitting, resampling of T2 image/mask to the T1 reference geometry, and residual displacement-field generation.
2. **Anatomical analysis (Slicer):** sphenoid coordinate frame and left/right fossa upper-surface extraction with four-part subdivision.
3. **Visualization (Slicer + external Python):** LR/AP/SI displacement heatmaps, surface/patch deformation views, and HTML export with direction labels and linked fossa selection.

The implementation is intended to preserve the existing registration algorithm. It does not automatically prove that a field is a forward or inverse mapping; confirm transform direction and geometry for each dataset.

## Repository layout

```text
CBCTTMJAnalysis/
├── CBCTTMJAnalysis.py
├── CBCTTMJAnalysisLib/
│   ├── registration_backend.py
│   └── visualization_exporter.py
├── assets/
│   └── annotation_interactions.js
├── docs/
│   └── INSTALL_PYTHON310.md
├── requirements_backend_py310.txt
├── install_requirements_py310.bat
├── verify_backend.py
├── .gitignore
└── README.md
```

## Requirements

- 3D Slicer 5.6.x (the module has been developed against Slicer 5.6.2).
- Windows 10/11, 64-bit.
- External Conda Python 3.10 environment for ANTsPy, SimpleITK, NiBabel, PyVista, VTK, and Trame. Keep these packages out of Slicer's bundled Python.

Pinned baseline dependencies are in [`requirements_backend_py310.txt`](requirements_backend_py310.txt). The VTK pin is intended to avoid the `vtkSerializationManager` DLL issue observed with VTK 9.7.1 in the development environment; this is a compatibility baseline, not a guarantee for every machine.

## Installation

See [`docs/INSTALL_PYTHON310.md`](docs/INSTALL_PYTHON310.md) for complete setup and validation steps.

Quick start in Anaconda Prompt:

```bat
conda create -n cbcttmj_py310 python=3.10 -y
conda activate cbcttmj_py310
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements_backend_py310.txt
python -m pip check
python verify_backend.py
```

Then add this repository folder (`CBCTTMJAnalysis`) to Slicer's **Edit → Application Settings → Modules → Additional module paths**, restart/reload the module, and set **External Python** to the environment's `python.exe`.

## Step 3 HTML export

`CBCTTMJAnalysisLib/visualization_exporter.py` contains the JavaScript payload used by the HTML exporter. The editable source is kept in `assets/annotation_interactions.js`. Generated HTML is written to the output directory selected by the module; check the Slicer log if export fails. Validate the generated HTML in the target browser, because WebGL/VTK rendering behavior can vary by environment.

## Data privacy

Do **not** commit patient scans, masks, segmentations, registration fields, screenshots containing identifiable data, or generated patient-specific HTML. These formats are excluded by `.gitignore` where practical. Use synthetic or properly de-identified data only when sharing examples.

## Known limitations

- `verify_backend.py` checks environment/import compatibility; it does not run a full registration test or certify displacement-field direction.
- The ANTsPy/SimpleITK/VTK stack includes native DLLs; mixing packages from multiple environments can cause import failures.
- HTML export and interaction must be tested on the actual target machine.

## License

No open-source license has been selected yet. Until a license is added, assume standard copyright applies; do not treat the repository as granting permission to reuse or redistribute the code.
