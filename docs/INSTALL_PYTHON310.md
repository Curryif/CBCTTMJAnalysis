# Installation: Slicer 5.6.x + external Python 3.10

## 1. Create the external environment

Open **Anaconda Prompt**:

```bat
conda create -n cbcttmj_py310 python=3.10 -y
conda activate cbcttmj_py310
```

Change directory to the repository root (the directory containing `requirements_backend_py310.txt`), then run:

```bat
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements_backend_py310.txt
python -m pip check
python verify_backend.py
```

You can also run `install_requirements_py310.bat` after activating this environment.

## 2. Set up the Slicer module

1. Keep the repository folder at a stable path, for example `D:\\code\\CBCTTMJAnalysis`.
2. Open Slicer 5.6.x.
3. Go to **Edit → Application Settings → Modules** and add the repository root to **Additional module paths**.
4. Restart Slicer or reload the module.
5. In the module's **External Python** field, choose the environment executable, for example `D:\\anaconda3\\envs\\cbcttmj_py310\\python.exe`.
6. Select the T1/T2 CBCT images and corresponding masks, or load existing registration outputs, and run the workflow one step at a time.

## 3. Verify the external environment

```bat
python -c "import sys, ants, SimpleITK, nibabel, numpy, scipy, pyvista, vtk; print(sys.executable); print('ANTsPy', ants.__version__); print('VTK', vtk.vtkVersion.GetVTKVersion())"
python -m pip check
python verify_backend.py
```

Make sure `sys.executable` is the intended Conda Python. Do not use Slicer's embedded Python for this backend.

## 4. Common problems

### `ModuleNotFoundError: No module named 'ants'`

The module's **External Python** path does not point to the environment where `import ants` succeeds. Select the exact `python.exe` printed by `sys.executable` in the test above.

### `ImportError: DLL load failed` from VTK or SciPy

Use a clean environment instead of upgrading/downgrading a mixed environment in place. Confirm 64-bit Python 3.10, reinstall from the pinned requirements, and run `python -m pip check`. Do not install these packages into Slicer's embedded Python.

### HTML export is missing

Inspect the Step 3 log for an HTML export failure. Verify the PyVista/VTK/Trame imports using the environment test above. A screenshot warning and an HTML export failure are different issues.

## 5. Validation checklist

- [ ] `verify_backend.py` exits successfully.
- [ ] The selected external interpreter is the intended Conda Python 3.10.
- [ ] T1/T2 image and mask geometries are checked before registration.
- [ ] Rigid and residual transforms are validated on the target dataset.
- [ ] LR/AP/SI heatmaps use the expected Slicer RAS coordinate convention.
- [ ] Step 3 HTML files open and both direction labels and linked fossa selection work.
- [ ] No identifiable patient data is included in a public repository.
