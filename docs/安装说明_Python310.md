# CBCT TMJ Analysis — Slicer 5.6.x + external Python 3.10

## Package contents

```text
CBCTTMJAnalysis/
├── CBCTTMJAnalysis.py
├── requirements_backend.txt
├── requirements_backend_py310.txt
├── install_requirements_py310.bat
├── verify_backend.py
├── wb_annotations_all_in_one(1).js       # Editable original JS source
├── README_Python310_安装说明.md
└── CBCTTMJAnalysisLib/
    ├── registration_backend.py
    └── visualization_exporter.py         # Includes the JS used by Step 3 HTML export
```

## Important environment separation

- Slicer UI/module runs inside Slicer's own Python.
- ANTsPy registration and PyVista/Trame HTML export run in an **external 64-bit Conda Python 3.10** environment.
- Do not install ANTsPy, SciPy, PyVista, or VTK into Slicer's bundled Python for this workflow.
- The module clears `PYTHONHOME` and `PYTHONPATH` for the external process to reduce Slicer/Conda ITK and VTK DLL conflicts.

## Recommended installation (Windows 10/11 x64)

Open **Anaconda Prompt** and run:

```bat
conda create -n cbcttmj_py310 python=3.10 -y
conda activate cbcttmj_py310
cd /d D:\path\to\CBCTTMJAnalysis
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements_backend_py310.txt
python -m pip check
python verify_backend.py
```

Replace `D:\path\to\CBCTTMJAnalysis` with the extracted folder path. Alternatively, after activating the correct Python 3.10 environment, double-click `install_requirements_py310.bat`.

The baseline pins `vtk==9.3.1` and `pyvista==0.44.2` rather than the newer VTK 9.7.1 stack, because the newer stack produced a `vtkSerializationManager` DLL load error in the reported environment. These are recommended compatibility pins, not a guarantee for every Windows installation; if pip reports a dependency conflict, do not force-install with `--no-deps`.

## Add the module to Slicer

1. Extract the entire `CBCTTMJAnalysis` folder to a stable path, for example `D:\download\CBCTTMJAnalysis`.
2. In Slicer 5.6.2, open **Edit → Application Settings → Modules**.
3. Add the folder containing `CBCTTMJAnalysis.py` to **Additional module paths**.
4. Restart Slicer or use the module reload function.
5. In the module's **External Python** field, select the environment's executable, e.g. `D:\anaconda3\envs\cbcttmj_py310\python.exe`.
6. Select T1/T2 images and masks, or load existing registration results, then run Steps 2 and 3.

## Step 3 HTML outputs

The `CBCTTMJAnalysisLib/visualization_exporter.py` file contains the supplied direction-label and linked fossa-selection JavaScript embedded in `ANNOTATION_JS_B64`. After Step 3, the exporter attempts to create:

- `local_patch_LR_with_anatomy.html`
- `local_patch_AP_with_anatomy.html`
- `local_patch_SI_with_anatomy.html`

Each successful HTML export receives the embedded JavaScript for direction labels and linked fossa selection. The original JS source is included separately for maintenance. The interaction still needs to be checked in the actual browser/HTML generated on the target machine; successful injection alone does not guarantee every browser/WebGL interaction works identically.

## Troubleshooting

### `ModuleNotFoundError: No module named 'ants'`

In the Slicer module, set **External Python** to the same `python.exe` where this command succeeds:

```bat
D:\anaconda3\envs\cbcttmj_py310\python.exe -c "import ants; print(ants.__version__)"
```

### `ImportError: DLL load failed ... vtkSerializationManager`

1. Activate the external Conda environment, not Slicer's Python.
2. Check that `PYTHONHOME` and `PYTHONPATH` are not set in the shell.
3. Run `python -m pip check` and `python verify_backend.py`.
4. If using the old environment with VTK 9.7.1, create a clean Python 3.10 environment and install the pinned requirements above rather than mixing VTK wheels from different versions.

### HTML is not generated

Review the Step 3 log for `[HTML EXPORT FAILED]`. HTML export requires a working VTK/PyVista/Trame stack. A PNG screenshot warning is separate from the HTML export result. Test the backend in the selected external Python environment first.

## Scope and limitations

- This package preserves the supplied ANTsPy SyNAggro + sphenoid Kabsch + residual-field workflow; it does not replace the registration algorithm.
- Check displacement-field direction and geometry before interpreting the heatmaps clinically.
- `verify_backend.py` checks Python version and dependency imports; it does not run registration or certify field direction.
