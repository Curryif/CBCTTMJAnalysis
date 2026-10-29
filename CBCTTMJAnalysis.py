# -*- coding: utf-8 -*-
"""CBCT TMJ Analysis: 3D Slicer Scripted Module."""
import os, sys, csv, json, traceback
import numpy as np
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from scipy import ndimage
from scipy.ndimage import map_coordinates

class CBCTTMJAnalysis(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CBCT TMJ Analysis"
        self.parent.categories = ["CBCT"]
        self.parent.dependencies = []
        self.parent.contributors = ["OpenAI"]
        self.parent.helpText = "Single-case CBCT registration, TMJ fossa surface extraction, directional displacement heatmaps, and patch deformation."
        self.parent.acknowledgementText = "Research prototype; validate field direction and geometry before scientific interpretation."

class CBCTTMJAnalysisWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = CBCTTMJAnalysisLogic()
        self.process = qt.QProcess()
        self.process.readyReadStandardOutput.connect(self.onProcessStdout)
        self.process.readyReadStandardError.connect(self.onProcessStderr)
        self.process.finished.connect(self.onProcessFinished)
        self.processPurpose = None
        self.outputDir = None
        self.analysisMaskNode = None
        self.t2RigidMaskNode = None
        self.t2RigidImageNode = None
        self.fieldData = None
        self.fieldAffine = None
        self.fieldPath = None
        self.axes = None
        self.directionModels = {}
        self.patchDirectionModels = {}
        self.regionModels = {}
        self.sideData = {}
        self.generatedModelNodes = []
        self.stage2Ready = False
        self.registrationReady = False

        inputBox = ctk.ctkCollapsibleButton(); inputBox.text = "Inputs"
        inputForm = qt.QFormLayout(inputBox); self.layout.addWidget(inputBox)
        self.t1Selector = self.volumeSelector("T1 CBCT image")
        self.t2Selector = self.volumeSelector("T2 CBCT image")
        self.t1MaskSelector = self.volumeSelector("T1 label mask; required for anatomical analysis")
        self.t2MaskSelector = self.volumeSelector("T2 label mask; required for registration")
        inputForm.addRow("T1 image:", self.t1Selector)
        inputForm.addRow("T2 image:", self.t2Selector)
        inputForm.addRow("T1 mask:", self.t1MaskSelector)
        inputForm.addRow("T2 mask:", self.t2MaskSelector)

        parameterBox = ctk.ctkCollapsibleButton(); parameterBox.text = "Parameters and backend"
        form = qt.QFormLayout(parameterBox); self.layout.addWidget(parameterBox)
        self.sphenoidLabel = self.spin(2, 0, 65535)
        self.fossaLabel = self.spin(4, 0, 65535)
        self.normalThreshold = qt.QDoubleSpinBox(); self.normalThreshold.minimum = -1.0; self.normalThreshold.maximum = 1.0; self.normalThreshold.singleStep = 0.05; self.normalThreshold.decimals = 2; self.normalThreshold.value = 0.30
        self.deformationScale = qt.QDoubleSpinBox(); self.deformationScale.minimum = 0.0; self.deformationScale.maximum = 20.0; self.deformationScale.singleStep = 0.5; self.deformationScale.decimals = 2; self.deformationScale.value = 3.0
        self.patchResolution = self.spin(55, 10, 150)
        self.pythonEdit = qt.QLineEdit(os.environ.get("CBCTTMJ_ANTSPY_PYTHON", ""))
        self.pythonEdit.placeholderText = "External Python with antspyx, SimpleITK, nibabel, NumPy and SciPy"
        pyRow = qt.QWidget(); pyLayout = qt.QHBoxLayout(pyRow); pyLayout.setContentsMargins(0,0,0,0); pyLayout.addWidget(self.pythonEdit)
        pyBrowse = qt.QPushButton("Browse…"); pyBrowse.clicked.connect(self.onBrowsePython); pyLayout.addWidget(pyBrowse)
        self.outputEdit = qt.QLineEdit(os.path.join(os.path.expanduser("~"), "CBCTTMJAnalysis"))
        outRow = qt.QWidget(); outLayout = qt.QHBoxLayout(outRow); outLayout.setContentsMargins(0,0,0,0); outLayout.addWidget(self.outputEdit)
        outBrowse = qt.QPushButton("Browse…"); outBrowse.clicked.connect(self.onBrowseOutput); outLayout.addWidget(outBrowse)
        form.addRow("Sphenoid label:", self.sphenoidLabel); form.addRow("Fossa label:", self.fossaLabel)
        form.addRow("Upper-surface normal threshold:", self.normalThreshold)
        form.addRow("Patch display scale:", self.deformationScale); form.addRow("Patch resolution:", self.patchResolution)
        form.addRow("External Python:", pyRow); form.addRow("Output folder:", outRow)

        existingBox = ctk.ctkCollapsibleButton(); existingBox.text = "Reuse existing registration results"
        existingForm = qt.QFormLayout(existingBox); self.layout.addWidget(existingBox)
        self.fieldPathEdit = qt.QLineEdit("")
        fieldRow = qt.QWidget(); fieldLayout = qt.QHBoxLayout(fieldRow); fieldLayout.setContentsMargins(0,0,0,0); fieldLayout.addWidget(self.fieldPathEdit)
        fieldBrowse = qt.QPushButton("Browse…"); fieldBrowse.clicked.connect(self.onBrowseField); fieldLayout.addWidget(fieldBrowse)
        self.rigidImagePathEdit = qt.QLineEdit("")
        rigidRow = qt.QWidget(); rigidLayout = qt.QHBoxLayout(rigidRow); rigidLayout.setContentsMargins(0,0,0,0); rigidLayout.addWidget(self.rigidImagePathEdit)
        rigidBrowse = qt.QPushButton("Browse…"); rigidBrowse.clicked.connect(self.onBrowseRigidImage); rigidLayout.addWidget(rigidBrowse)
        existingForm.addRow("Residual field (.nii/.nii.gz):", fieldRow)
        existingForm.addRow("T2 rigid image (.nii/.nii.gz):", rigidRow)
        self.loadExistingButton = qt.QPushButton("Load existing results (skip registration)")
        self.loadExistingButton.clicked.connect(self.onLoadExisting)
        existingForm.addRow(self.loadExistingButton)

        workflowBox = ctk.ctkCollapsibleButton(); workflowBox.text = "Three-step workflow"
        workflowForm = qt.QFormLayout(workflowBox); self.layout.addWidget(workflowBox)
        self.runButton = qt.QPushButton("Step 1: Run registration only")
        self.runButton.clicked.connect(self.onRunRegistration); workflowForm.addRow(self.runButton)
        self.step2Button = qt.QPushButton("Step 2: Extract anatomy and split each fossa into 4 regions")
        self.step2Button.clicked.connect(self.onRunStage2); workflowForm.addRow(self.step2Button)
        self.step3Button = qt.QPushButton("Step 3: Calculate and visualize displacement")
        self.step3Button.clicked.connect(self.onRunStage3); workflowForm.addRow(self.step3Button)
        self.direction = qt.QComboBox(); self.direction.addItems(["SI", "LR", "AP"]); self.direction.currentIndexChanged.connect(self.onDirectionChanged)
        workflowForm.addRow("Visible displacement direction:", self.direction)
        self.showRegionsCheckBox = qt.QCheckBox("Show the four regions on each upper surface")
        self.showRegionsCheckBox.checked = True
        self.showRegionsCheckBox.stateChanged.connect(self.onRegionVisibilityChanged)
        workflowForm.addRow(self.showRegionsCheckBox)
        saveButton = qt.QPushButton("Save Slicer scene (.mrb)"); saveButton.clicked.connect(self.onSaveScene); workflowForm.addRow(saveButton)

        self.progress = qt.QProgressBar(); self.progress.minimum = 0; self.progress.maximum = 0; self.progress.visible = False; self.layout.addWidget(self.progress)
        logBox = ctk.ctkCollapsibleButton(); logBox.text = "Log"; logLayout = qt.QVBoxLayout(logBox)
        self.logText = qt.QPlainTextEdit(); self.logText.readOnly = True; self.logText.minimumHeight = 170; logLayout.addWidget(self.logText); self.layout.addWidget(logBox)
        self.layout.addStretch(1)

    def volumeSelector(self, tooltip):
        w = slicer.qMRMLNodeComboBox(); w.nodeTypes = ["vtkMRMLScalarVolumeNode", "vtkMRMLLabelMapVolumeNode"]
        w.selectNodeUponCreation = False; w.addEnabled = True; w.removeEnabled = False; w.noneEnabled = True
        w.showHidden = False; w.showChildNodeTypes = True; w.setMRMLScene(slicer.mrmlScene); w.toolTip = tooltip
        return w

    def spin(self, value, minimum, maximum):
        w = qt.QSpinBox(); w.minimum = minimum; w.maximum = maximum; w.value = value; return w

    def log(self, text): self.logText.appendPlainText(str(text)); slicer.app.processEvents()

    def onBrowsePython(self):
        path = qt.QFileDialog.getOpenFileName(slicer.util.mainWindow(), "Select external Python", "", "Python executable (python.exe);;All files (*)")
        if path: self.pythonEdit.text = path

    def onBrowseOutput(self):
        path = qt.QFileDialog.getExistingDirectory(slicer.util.mainWindow(), "Select output folder", self.outputEdit.text)
        if path: self.outputEdit.text = path

    def onBrowseField(self):
        path = qt.QFileDialog.getOpenFileName(slicer.util.mainWindow(), "Select residual displacement field", self.fieldPathEdit.text, "NIfTI files (*.nii *.nii.gz);;All files (*)")
        if path: self.fieldPathEdit.text = path

    def onBrowseRigidImage(self):
        path = qt.QFileDialog.getOpenFileName(slicer.util.mainWindow(), "Select T2 rigid image", self.rigidImagePathEdit.text, "NIfTI files (*.nii *.nii.gz);;All files (*)")
        if path: self.rigidImagePathEdit.text = path

    def externalEnvironment(self, pythonExe):
        env = qt.QProcessEnvironment.systemEnvironment()
        for key in ["PYTHONHOME", "PYTHONPATH", "ITK_AUTOLOAD_PATH", "ITK_AUTOLOAD_DIR"]:
            env.remove(key)
        prefix = os.path.dirname(os.path.abspath(pythonExe))
        env.insert("CONDA_PREFIX", prefix)
        env.insert("CONDA_DEFAULT_ENV", os.path.basename(prefix))
        oldPath = str(env.value("PATH"))
        entries = [x for x in oldPath.split(os.pathsep) if x]
        slicerRoot = os.path.normcase(os.path.abspath(slicer.app.applicationDirPath()))
        kept = []
        for entry in entries:
            normEntry = os.path.normcase(os.path.abspath(entry))
            if normEntry.startswith(slicerRoot):
                continue
            if "slicer.org" in normEntry.replace(chr(92), "/").lower():
                continue
            kept.append(entry)
        condaEntries = [prefix, os.path.join(prefix, "Library", "bin"), os.path.join(prefix, "Scripts"), os.path.join(prefix, "DLLs")]
        env.insert("PATH", os.pathsep.join([x for x in condaEntries if os.path.isdir(x)] + kept))
        return env

    def startExternalProcess(self, pythonExe, args, purpose):
        self.processPurpose = purpose
        self.process.setProcessEnvironment(self.externalEnvironment(pythonExe))
        self.process.setWorkingDirectory(self.outputDir)
        self.runButton.enabled = False
        self.loadExistingButton.enabled = False
        self.step2Button.enabled = False
        self.step3Button.enabled = False
        self.progress.visible = True
        self.log("Backend executable: " + pythonExe)
        self.log("Process purpose: " + purpose)
        self.process.start(pythonExe, args)

    def onRunRegistration(self):
        if self.process.state() != qt.QProcess.NotRunning:
            slicer.util.errorDisplay("A backend process is already running."); return
        nodes = [self.t1Selector.currentNode(), self.t2Selector.currentNode(), self.t1MaskSelector.currentNode(), self.t2MaskSelector.currentNode()]
        if not all(nodes):
            slicer.util.errorDisplay("Select T1 image, T2 image, T1 mask, and T2 mask before registration."); return
        pythonExe = self.pythonEdit.text.strip()
        if not pythonExe or not os.path.isfile(pythonExe):
            slicer.util.errorDisplay("Choose an external python.exe with antspyx, SimpleITK, nibabel, NumPy and SciPy installed."); return
        outputText = self.outputEdit.text.strip()
        if not outputText: slicer.util.errorDisplay("Choose an output folder."); return
        self.outputDir = os.path.abspath(outputText)
        os.makedirs(self.outputDir, exist_ok=True)
        inDir = os.path.join(self.outputDir, "inputs"); os.makedirs(inDir, exist_ok=True)
        paths = [os.path.join(inDir, n) for n in ["T1_img.nii.gz", "T2_img.nii.gz", "T1_mask.nii.gz", "T2_mask.nii.gz"]]
        try:
            for node, path in zip(nodes, paths):
                if not slicer.util.saveNode(node, path): raise RuntimeError("Could not save " + node.GetName())
        except Exception as e:
            slicer.util.errorDisplay("Could not save input volumes:\n" + str(e)); return
        backend = os.path.join(os.path.dirname(__file__), "CBCTTMJAnalysisLib", "registration_backend.py")
        if not os.path.isfile(backend):
            slicer.util.errorDisplay("Registration backend not found: " + backend); return
        args = [backend, "--t1", paths[0], "--t2", paths[1], "--t1-mask", paths[2], "--t2-mask", paths[3],
                "--out", self.outputDir, "--sphenoid-label", str(self.sphenoidLabel.value), "--fossa-label", str(self.fossaLabel.value)]
        self.logText.clear(); self.log("Starting registration backend."); self.log("Output: " + self.outputDir)
        self.startExternalProcess(pythonExe, args, "registration")

    def onLoadExisting(self):
        if self.process.state() != qt.QProcess.NotRunning:
            slicer.util.errorDisplay("A backend process is already running."); return
        if self.t1MaskSelector.currentNode() is None:
            slicer.util.errorDisplay("Select the T1 label mask. It is required for Step 2."); return
        fieldPath = os.path.abspath(self.fieldPathEdit.text.strip())
        rigidPath = os.path.abspath(self.rigidImagePathEdit.text.strip())
        if not os.path.isfile(fieldPath):
            slicer.util.errorDisplay("Residual field not found:\n" + fieldPath); return
        if not os.path.isfile(rigidPath):
            slicer.util.errorDisplay("T2 rigid image not found:\n" + rigidPath); return
        self.fieldPath = fieldPath
        self.rigidImagePathEdit.text = rigidPath
        outputText = self.outputEdit.text.strip()
        self.outputDir = os.path.abspath(outputText) if outputText else os.path.dirname(fieldPath)
        self.outputEdit.text = self.outputDir
        os.makedirs(self.outputDir, exist_ok=True)
        npzPath = os.path.join(self.outputDir, "T2_residual_elastic_field_ras.npz")
        sameFieldFolder = os.path.normcase(os.path.dirname(fieldPath)) == os.path.normcase(self.outputDir)
        reusable = sameFieldFolder and os.path.isfile(npzPath) and os.path.getmtime(npzPath) >= os.path.getmtime(fieldPath)
        self.logText.clear(); self.log("Loading existing registration results; registration will not be rerun.")
        self.log("Residual field: " + fieldPath); self.log("T2 rigid image: " + rigidPath)
        if reusable:
            try:
                self.loadRegistrationArtifacts(npzPath, rigidPath)
                self.log("Existing results loaded. You can now run Step 2.")
            except Exception as e:
                self.log(traceback.format_exc()); slicer.util.errorDisplay("Could not load existing results:\n" + str(e))
            return
        pythonExe = self.pythonEdit.text.strip()
        if not pythonExe or not os.path.isfile(pythonExe):
            slicer.util.errorDisplay("An external Python with nibabel, NumPy and SciPy is needed to import this NIfTI vector field. Select python.exe first."); return
        backend = os.path.join(os.path.dirname(__file__), "CBCTTMJAnalysisLib", "registration_backend.py")
        args = [backend, "--prepare-existing-field", fieldPath, "--field-npz-output", npzPath]
        self.startExternalProcess(pythonExe, args, "prepare_field")

    def onRunStage2(self):
        try:
            self.runStage2()
        except Exception as e:
            self.log(traceback.format_exc()); slicer.util.errorDisplay("Step 2 failed:\n" + str(e))

    def onRunStage3(self):
        try:
            self.runStage3()
        except Exception as e:
            self.log(traceback.format_exc()); slicer.util.errorDisplay("Step 3 failed:\n" + str(e))

    def qByteArrayToText(self, data):
        """兼容 Slicer 5.6.2 PythonQt 的 QByteArray 转文本方式。"""
        if data is None:
            return ""

        # 优先使用 PythonQt 的 data() 方法
        try:
            raw = data.data()
        except Exception:
            raw = data

        # 已经是 Python 字符串
        if isinstance(raw, str):
            return raw

        # 标准 Python 字节类型
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")

        if isinstance(raw, bytearray):
            return raw.decode("utf-8", errors="replace")

        # 兼容可能返回 QByteArray 或其他 Qt 类型的情况
        try:
            decoded = raw.decode("utf-8", errors="replace")
            if isinstance(decoded, str):
                return decoded
        except Exception:
            pass

        # 尝试 Qt 字符串转换接口
        try:
            raw = data.toStdString()
            if isinstance(raw, str):
                return raw
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace")
        except Exception:
            pass

        # 最后的兼容处理
        try:
            return str(raw)
        except Exception:
            return ""


    def onProcessStdout(self):
        """读取外部配准进程的标准输出。"""
        try:
            data = self.process.readAllStandardOutput()
            text = self.qByteArrayToText(data)
            if text:
                self.logText.appendPlainText(text.rstrip("\r\n"))
                slicer.app.processEvents()
        except Exception:
            self.logText.appendPlainText(
                "读取标准输出失败：\n" + traceback.format_exc()
            )


    def onProcessStderr(self):
        """读取外部配准进程的标准错误输出。"""
        try:
            data = self.process.readAllStandardError()
            text = self.qByteArrayToText(data)
            if text:
                self.logText.appendPlainText(text.rstrip("\r\n"))
                slicer.app.processEvents()
        except Exception:
            self.logText.appendPlainText(
                "读取标准错误失败：\n" + traceback.format_exc()
            )


    def onProcessFinished(self, exitCode, exitStatus=None):
        self.runButton.enabled = True
        self.loadExistingButton.enabled = True
        self.step2Button.enabled = True
        self.step3Button.enabled = True
        self.progress.visible = False
        try: code = int(exitCode)
        except Exception: code = -1
        if exitStatus is not None: self.log("Process exit status: {}".format(exitStatus))
        self.log("Backend process finished. Exit code: {}".format(code))
        purpose = self.processPurpose
        self.processPurpose = None
        if code != 0:
            self.log("Backend failed. Review the preceding error messages.")
            slicer.util.errorDisplay("External process failed with exit code {}. Check the Log panel.".format(code))
            return
        try:
            if purpose == "registration":
                self.fieldPath = os.path.join(self.outputDir, "T2_residual_elastic_field.nii.gz")
                rigidPath = os.path.join(self.outputDir, "T2_warped_img_nihe_rigid.nii.gz")
                self.fieldPathEdit.text = self.fieldPath
                self.rigidImagePathEdit.text = rigidPath
                npzPath = os.path.join(self.outputDir, "T2_residual_elastic_field_ras.npz")
                self.loadRegistrationArtifacts(npzPath, rigidPath)
                self.log("STEP 1 COMPLETE: registration outputs are ready. Step 2 has not been run automatically.")
            elif purpose == "prepare_field":
                rigidPath = self.rigidImagePathEdit.text.strip()
                npzPath = os.path.join(self.outputDir, "T2_residual_elastic_field_ras.npz")
                self.loadRegistrationArtifacts(npzPath, rigidPath)
                self.log("Existing registration outputs loaded. Registration was skipped; you can now run Step 2.")
            elif purpose == "html_stage2":
                self.log("STEP 2 HTML export completed. Open stage2_anatomy_regions.html in a browser.")
            elif purpose == "html_stage3":
                self.log("STEP 3 HTML export completed. Open local_patch_LR_with_anatomy.html, local_patch_AP_with_anatomy.html, and local_patch_SI_with_anatomy.html in a browser.")
            else:
                self.log("Backend completed, but no matching workflow action was recorded.")
        except Exception as e:
            self.log(traceback.format_exc())
            slicer.util.errorDisplay("Could not load registration outputs:\n" + str(e))

    def loadRegistrationArtifacts(self, npzPath, rigidImagePath):
        if not os.path.isfile(npzPath): raise FileNotFoundError("RAS field cache not found: " + npzPath)
        if not os.path.isfile(rigidImagePath): raise FileNotFoundError("T2 rigid image not found: " + rigidImagePath)
        self.removeGeneratedNodes()
        f = np.load(npzPath)
        field = np.asarray(f["data"], dtype=np.float32)
        affine = np.asarray(f["affine"], dtype=np.float64)
        if field.ndim != 4 or field.shape[-1] != 3: raise ValueError("Field must have shape (I,J,K,3).")
        if not np.all(np.isfinite(affine)) or affine.shape != (4,4): raise ValueError("Invalid field affine.")
        if not np.all(np.isfinite(field)): raise ValueError("Residual field contains NaN or Inf values.")
        self.fieldData = field; self.fieldAffine = affine; self.fieldPath = self.fieldPathEdit.text.strip() or os.path.join(self.outputDir, "T2_residual_elastic_field.nii.gz")
        self.registrationReady = True
        # Remove prior output volumes to avoid duplicate nodes when reloading results.
        for node in list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
            if node.GetName().startswith("CBCTTMJ_Output_"): slicer.mrmlScene.RemoveNode(node)
        alignedMaskPath = self.logic.firstExistingPath([os.path.join(self.outputDir, "T1_mask_on_T1_grid.nii.gz"), os.path.join(os.path.dirname(rigidImagePath), "T1_mask_on_T1_grid.nii.gz"), os.path.join(os.path.dirname(self.fieldPath), "T1_mask_on_T1_grid.nii.gz")])
        if alignedMaskPath:
            self.analysisMaskNode = slicer.util.loadVolume(alignedMaskPath)
            self.analysisMaskNode.SetName("CBCTTMJ_Output_T1_mask_on_T1_grid")
        else:
            self.analysisMaskNode = self.t1MaskSelector.currentNode()
        if self.analysisMaskNode is None: raise ValueError("Select a T1 mask or provide T1_mask_on_T1_grid.nii.gz in the output folder.")
        self.t2RigidImageNode = slicer.util.loadVolume(rigidImagePath)
        self.t2RigidImageNode.SetName("CBCTTMJ_Output_T2_warped_img_nihe_rigid")
        rigidMaskPath = self.logic.firstExistingPath([os.path.join(self.outputDir, "T2_warped_mask_nihe_rigid.nii.gz"), os.path.join(os.path.dirname(rigidImagePath), "T2_warped_mask_nihe_rigid.nii.gz"), os.path.join(os.path.dirname(self.fieldPath), "T2_warped_mask_nihe_rigid.nii.gz")])
        self.t2RigidMaskNode = None
        if rigidMaskPath:
            self.t2RigidMaskNode = slicer.util.loadVolume(rigidMaskPath)
            self.t2RigidMaskNode.SetName("CBCTTMJ_Output_T2_warped_mask_nihe_rigid")
        self.log("Field loaded: shape={}, vectors=RAS, affine=RAS.".format(tuple(field.shape)))
        self.log("T2 rigid image loaded into Slicer: " + rigidImagePath)
        self.log("Analysis mask: " + self.analysisMaskNode.GetName())
        # Report geometry mismatch but sample by physical RAS coordinates, not array-index coincidence.
        matrix = vtk.vtkMatrix4x4(); self.analysisMaskNode.GetIJKToRASMatrix(matrix)
        maskAffine = np.array([[matrix.GetElement(r,c) for c in range(4)] for r in range(4)], dtype=np.float64)
        if not np.allclose(maskAffine, affine, atol=1e-3, rtol=0):
            self.log("NOTE: T1 mask and field grids differ. Field sampling will use physical RAS coordinates and the field affine.")

    def onDirectionChanged(self, *args):
        mode = str(self.direction.currentText)
        for (side, direction), node in self.directionModels.items(): node.GetDisplayNode().SetVisibility(direction == mode)
        for (side, direction), node in self.patchDirectionModels.items(): node.GetDisplayNode().SetVisibility(direction == mode)

    def onRegionVisibilityChanged(self, *args):
        visible = bool(self.showRegionsCheckBox.checked)
        # Keep heatmaps readable when region overlays are enabled during Step 3.
        opacity = 0.22 if self.directionModels else 0.95
        for node in self.regionModels.values():
            if node and node.GetDisplayNode():
                node.GetDisplayNode().SetOpacity(opacity)
                node.GetDisplayNode().SetVisibility(visible)

    def startHtmlExport(self, stage):
        """Export interactive PyVista HTML files using the configured external Python."""
        pythonExe = self.pythonEdit.text.strip()
        exporter = os.path.join(os.path.dirname(__file__), "CBCTTMJAnalysisLib", "visualization_exporter.py")
        if not pythonExe or not os.path.isfile(pythonExe):
            self.log("HTML export skipped: choose the external Python environment to enable PyVista HTML export.")
            return False
        if not os.path.isfile(exporter):
            self.log("HTML export skipped: exporter script not found: " + exporter)
            return False
        args = [exporter, "--stage", str(int(stage)), "--out", self.outputDir,
                "--scale", str(float(self.deformationScale.value))]
        self.log("Starting interactive HTML export for Step {}.".format(stage))
        self.startExternalProcess(pythonExe, args, "html_stage{}".format(int(stage)))
        return True

    def runStage2(self):
        maskNode = self.analysisMaskNode or self.t1MaskSelector.currentNode()
        if maskNode is None: raise ValueError("Select the T1 mask before Step 2.")
        self.analysisMaskNode = maskNode
        self.outputDir = os.path.abspath(self.outputEdit.text.strip()); os.makedirs(self.outputDir, exist_ok=True)
        self.removeGeneratedNodes()
        sphLabel, fossaLabel = int(self.sphenoidLabel.value), int(self.fossaLabel.value)
        t1Array = slicer.util.arrayFromVolume(maskNode)
        sphenoid = self.logic.maskToRASPolyData(t1Array == sphLabel, maskNode)
        if sphenoid.GetNumberOfPoints() < 10: raise ValueError("Sphenoid label {} not found or too small.".format(sphLabel))
        self.axes = self.logic.pcaAxesRAS(sphenoid)
        axesJson = {k: np.asarray(self.axes[k]).tolist() for k in ["origin", "LR", "AP", "SI"]}
        with open(os.path.join(self.outputDir, "sphenoid_coordinate.json"), "w", encoding="utf-8") as f: json.dump(axesJson, f, indent=2)
        self.log("Step 2: sphenoid coordinate system in Slicer RAS:")
        for key in ["LR", "AP", "SI"]: self.log("{} = {}".format(key, np.array2string(self.axes[key], precision=4)))
        self.addAndSaveModel(sphenoid, "CBCTTMJ_Model_Sphenoid", (0.78,0.70,0.52), 0.22, "sphenoid_T1.vtp")
        axisParts = []
        for name, color in [("LR", (0.9,0.1,0.1)), ("AP", (0.1,0.7,0.2)), ("SI", (0.1,0.25,0.95))]:
            axisPoly = self.logic.makeAxisArrow(self.axes["origin"], self.axes[name], 30.0)
            self.addAndSaveModel(axisPoly, "CBCTTMJ_Axis_" + name, color, 1.0, "axis_" + name + ".vtp")
            axisParts.append(axisPoly)
        append = vtk.vtkAppendPolyData()
        for axisPoly in axisParts: append.AddInputData(axisPoly)
        append.Update(); self.logic.savePolyData(append.GetOutput(), os.path.join(self.outputDir, "sphenoid_coordinate_axis.vtp"))

        components = self.logic.fossaComponents(maskNode, fossaLabel)
        if len(components) < 2: raise ValueError("Expected two disconnected T1 fossa components for label {}. Found {}.".format(fossaLabel, len(components)))
        # Step 2 deliberately displays T1 anatomy only; registration outputs are used in Step 3.
        fossaInfo = {}
        self.sideData = {}
        regionColors = [(0.90,0.25,0.22),(0.98,0.62,0.20),(0.25,0.55,0.88),(0.55,0.35,0.75)]
        for side in ["left", "right"]:
            comp = components[0 if side == "left" else 1]
            full = self.logic.maskToRASPolyData(comp["mask"], maskNode)
            upper = self.logic.extractUpperSurface(full, self.axes["SI"], float(self.normalThreshold.value))
            if upper.GetNumberOfPoints() < 20: raise ValueError(side + " upper surface is too small; lower the normal threshold or inspect label segmentation.")
            regions = self.logic.splitRegions(upper, self.axes)
            # Keep full fossa and complete upper-surface meshes as analysis/export assets,
            # but do not display them in Step 2. Only the four T1 region surfaces are shown.
            t2Full = None; t2Upper = None
            self.logic.savePolyData(full, os.path.join(self.outputDir, side + "_full_fossa.vtp"))
            self.logic.savePolyData(upper, os.path.join(self.outputDir, side + "_upper_surface.vtp"))
            regionSummary = []
            for idx, item in enumerate(regions, 1):
                regionPoly = item["poly"]
                if regionPoly.GetNumberOfCells() == 0: continue
                node = self.logic.addModel(regionPoly, "CBCTTMJ_Region_{}_{}".format(side, idx), regionColors[idx-1], 0.95)
                self.generatedModelNodes.append(node); self.regionModels[(side,idx)] = node
                self.logic.savePolyData(regionPoly, os.path.join(self.outputDir, "{}_T1_upper_region_{}.vtp".format(side, idx)))
                self.logic.savePolyData(regionPoly, os.path.join(self.outputDir, "{}_region_{}.vtp".format(side, idx)))
                regionSummary.append({"region": idx, "area_mm2": item["area_mm2"], "area_ratio_percent": item["area_ratio_percent"]})
                self.log("{} Region {}: area={:.3f} mm^2 ({:.2f}%)".format(side.upper(), idx, item["area_mm2"], item["area_ratio_percent"]))
            self.sideData[side] = {"t1Full": full, "t1Upper": upper, "t2Full": t2Full, "t2Upper": t2Upper, "regions": regions, "component": comp}
            fossaInfo[side] = {"component_id": int(comp["component_id"]), "centroid_RAS_mm": np.asarray(comp["centerRAS"]).tolist(), "voxel_count": int(comp["size"]), "regions": regionSummary, "has_T2rigid_mask_surface": bool(t2Upper is not None)}
        with open(os.path.join(self.outputDir, "fossa_left_right_info.json"), "w", encoding="utf-8") as f: json.dump(fossaInfo, f, indent=2)
        self.stage2Ready = True
        self.onRegionVisibilityChanged()
        slicer.util.resetThreeDViews()
        self.log("STEP 2 COMPLETE: display contains only the T1 left/right four-region surfaces, sphenoid, and LR/AP/SI coordinate axes.")
        self.log("Full fossa and complete upper surfaces are saved as files but are not displayed in Step 2.")
        self.log("Click Step 3 to overlay displacement heatmaps and directionally deformed patches.")
        self.startHtmlExport(2)

    def runStage3(self):
        if not self.stage2Ready or not self.sideData: raise RuntimeError("Run Step 2 first.")
        if self.fieldData is None or self.fieldAffine is None: raise RuntimeError("Load existing registration results or run Step 1 first.")
        self.outputDir = os.path.abspath(self.outputEdit.text.strip()); os.makedirs(self.outputDir, exist_ok=True)
        self.removeVisualizationNodes()
        # Heatmaps occupy the same T1 surface as the region fills. Hide the fills in
        # the Slicer view and retain their boundaries so heatmap colors remain readable.
        self.showRegionsCheckBox.checked = False
        self.onRegionVisibilityChanged()
        regionLineColors = {"left":(0.95,0.95,0.95), "right":(0.10,0.10,0.10)}
        for side in ["left", "right"]:
            edgeParts = []
            for item in self.sideData[side]["regions"]:
                regionPoly = item["poly"]
                if regionPoly.GetNumberOfCells() == 0: continue
                edges = vtk.vtkFeatureEdges(); edges.SetInputData(regionPoly); edges.BoundaryEdgesOn(); edges.FeatureEdgesOff(); edges.ManifoldEdgesOff(); edges.NonManifoldEdgesOff(); edges.Update()
                if edges.GetOutput().GetNumberOfCells():
                    shifted = self.logic.copyPolyWithPoints(edges.GetOutput(), vtk_to_numpy(edges.GetOutput().GetPoints().GetData()).astype(float) + 0.03*np.asarray(self.axes["SI"])[None,:])
                    edgeParts.append(shifted)
            if edgeParts:
                appendEdges = vtk.vtkAppendPolyData()
                for edgePoly in edgeParts: appendEdges.AddInputData(edgePoly)
                appendEdges.Update()
                edgeNode = self.logic.addModel(appendEdges.GetOutput(), "CBCTTMJ_RegionBoundary_" + side, regionLineColors[side], 1.0)
                edgeNode.GetDisplayNode().SetLineWidth(2.0)
                self.generatedModelNodes.append(edgeNode)
                self.logic.savePolyData(appendEdges.GetOutput(), os.path.join(self.outputDir, side + "_T1_region_boundaries.vtp"))
        prepared = {}
        allScalars = []
        for side in ["left", "right"]:
            upper = self.sideData[side]["t1Upper"]
            points = vtk_to_numpy(upper.GetPoints().GetData()).astype(np.float64)
            disp, valid, invInfo = self.logic.inverseDisplacement(points, self.fieldData, self.fieldAffine)
            components = {k: disp @ self.axes[k] for k in ["LR", "AP", "SI"]}
            prepared[side] = {"disp": disp, "valid": valid, "components": components, "inverseInfo": invInfo}
            for mode in ["LR", "AP", "SI"]: allScalars.append(components[mode][valid])
            self.log("{} inverse-field valid ratio: {:.2f}% (iterations={}, converged={})".format(side.upper(), valid.mean()*100.0, invInfo["iterations"], invInfo["converged_to_tolerance"]))
            if valid.mean() < 0.95: self.log("WARNING: low field valid ratio on {}. Check field geometry and vector convention.".format(side))
        vmax = self.logic.symmetricRange(allScalars)
        self.log("Shared LR/AP/SI heatmap range: +/- {:.4f} mm".format(vmax))
        report = {"coordinate_system":"Slicer RAS", "field_vector_components":"RAS", "field_assumption":"T2-rigid -> T1; inverse field approximates T1 -> T2-rigid", "inverse_method":"fixed-point iteration x_(n+1)=y-u(x_n)", "normal_threshold":float(self.normalThreshold.value), "patch_display_scale":float(self.deformationScale.value), "patch_resolution":int(self.patchResolution.value), "shared_heatmap_range_mm":[-vmax,vmax], "axes":{k:np.asarray(self.axes[k]).tolist() for k in ["origin","LR","AP","SI"]}, "field_shape_IJK3":list(self.fieldData.shape), "field_affine_RAS":self.fieldAffine.tolist(), "sides":{}}
        localPatchStats = {}
        for side in ["left", "right"]:
            upper = self.sideData[side]["t1Upper"]
            points = vtk_to_numpy(upper.GetPoints().GetData()).astype(np.float64)
            disp = prepared[side]["disp"]; valid = prepared[side]["valid"]; components = prepared[side]["components"]
            mappedPoints = points.copy(); mappedPoints[valid] += disp[valid]
            mappedSurface = self.logic.copyPolyWithPoints(upper, mappedPoints)
            mappedNode = self.logic.addModel(mappedSurface, "CBCTTMJ_Mapped_{}_T1_surface_to_T2rigid".format(side), (0.98,0.72,0.20), 0.45)
            self.generatedModelNodes.append(mappedNode)
            self.logic.savePolyData(mappedSurface, os.path.join(self.outputDir, "{}_T1_upper_mapped_to_T2rigid.vtp".format(side)))
            for mode in ["LR", "AP", "SI"]:
                heatPoly = self.logic.polyDataWithScalars(upper, "U_{}_mm".format(mode), components[mode])
                heatNode = self.logic.addScalarModel(heatPoly, "CBCTTMJ_Heatmap_{}_{}".format(side, mode), "U_{}_mm".format(mode), vmax, 0.98)
                self.generatedModelNodes.append(heatNode); self.directionModels[(side,mode)] = heatNode
                self.logic.savePolyData(heatPoly, os.path.join(self.outputDir, "{}_T1_upper_heatmap_{}.vtp".format(side, mode)))
            patchBase, patchDisp, patchValid, patchComponents = self.logic.makePatch(upper, self.axes, self.fieldData, self.fieldAffine, int(self.patchResolution.value), 0.8)
            original = self.logic.addModel(patchBase, "CBCTTMJ_Patch_{}_original".format(side), (0.18,0.18,0.18), 0.85)
            original.GetDisplayNode().SetRepresentation(1); original.GetDisplayNode().SetLineWidth(1.4); self.generatedModelNodes.append(original)
            self.logic.savePolyData(patchBase, os.path.join(self.outputDir, side + "_patch_original.vtp"))
            patchWorld = vtk.vtkPolyData(); patchWorld.DeepCopy(patchBase)
            for compName, compValues in patchComponents.items():
                arr = numpy_to_vtk(np.nan_to_num(compValues, nan=0.0).astype(np.float32), deep=True, array_type=vtk.VTK_FLOAT)
                arr.SetName("Magnitude" if compName == "MAG" else "U_" + compName)
                patchWorld.GetPointData().AddArray(arr)
            validArray = numpy_to_vtk(patchValid.astype(np.uint8), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR); validArray.SetName("Valid"); patchWorld.GetPointData().AddArray(validArray)
            self.logic.savePolyData(patchWorld, os.path.join(self.outputDir, side + "_world_patch.vtp"))
            for mode in ["LR", "AP", "SI"]:
                deformed = self.logic.deformPatch(patchBase, patchDisp, patchValid, patchComponents[mode], self.axes[mode], mode, float(self.deformationScale.value))
                node = self.logic.addScalarModel(deformed, "CBCTTMJ_Patch_{}_deformed_{}".format(side, mode), "U_{}_mm".format(mode), vmax, 0.98)
                self.generatedModelNodes.append(node); self.patchDirectionModels[(side,mode)] = node
                self.logic.savePolyData(deformed, os.path.join(self.outputDir, "{}_patch_deformed_{}.vtp".format(side, mode)))
            self.logic.writeRegionStats(side, upper, disp, valid, self.axes, os.path.join(self.outputDir, side + "_region_displacement_stats.csv"))
            good = valid & np.all(np.isfinite(disp), axis=1)
            pts = vtk_to_numpy(upper.GetPoints().GetData()).astype(np.float64); rel = pts - pts.mean(axis=0)
            uRange = float((rel @ self.axes["LR"]).max() - (rel @ self.axes["LR"]).min())
            vRange = float((rel @ self.axes["AP"]).max() - (rel @ self.axes["AP"]).min())
            report["sides"][side] = {"valid_ratio":float(valid.mean()), "mean_magnitude_mm":float(np.mean(np.linalg.norm(disp[good],axis=1))) if np.any(good) else None, "mean_LR_mm":float(np.mean(components["LR"][good])) if np.any(good) else None, "mean_AP_mm":float(np.mean(components["AP"][good])) if np.any(good) else None, "mean_SI_mm":float(np.mean(components["SI"][good])) if np.any(good) else None, "inverse_iterations":int(prepared[side]["inverseInfo"]["iterations"]), "inverse_converged":bool(prepared[side]["inverseInfo"]["converged_to_tolerance"])}
            patchGood = patchValid & np.all(np.isfinite(patchDisp), axis=1)
            patchMag = np.linalg.norm(patchDisp[patchGood], axis=1) if np.any(patchGood) else np.array([])
            patchPts = vtk_to_numpy(patchBase.GetPoints().GetData()).astype(np.float64)
            patchRel = patchPts - points.mean(axis=0)
            patchURange = float((patchRel @ self.axes["LR"]).max() - (patchRel @ self.axes["LR"]).min())
            patchVRange = float((patchRel @ self.axes["AP"]).max() - (patchRel @ self.axes["AP"]).min())
            localPatchStats[side] = {"side":side, "valid_ratio":float(patchValid.mean()), "patch_mean_magnitude_mm":float(np.mean(patchMag)) if len(patchMag) else None, "patch_mean_LR_mm":float(np.mean(patchComponents["LR"][patchGood])) if np.any(patchGood) else None, "patch_mean_AP_mm":float(np.mean(patchComponents["AP"][patchGood])) if np.any(patchGood) else None, "patch_mean_SI_mm":float(np.mean(patchComponents["SI"][patchGood])) if np.any(patchGood) else None, "patch_u_range_mm":patchURange, "patch_v_range_mm":patchVRange}
            t2Upper = self.sideData[side].get("t2Upper")
            if t2Upper is not None:
                check = self.logic.fieldDirectionCheck(upper, t2Upper, self.fieldData, self.fieldAffine)
                self.log("{} T2-rigid surface check (mean point-to-surface distance, mm): before={:.3f}, after field={:.3f}".format(side.upper(), check["before_mean_mm"], check["after_mean_mm"]))
                report["sides"][side]["T2_surface_distance_before_mm"] = check["before_mean_mm"]
                report["sides"][side]["T2_surface_distance_after_field_mm"] = check["after_mean_mm"]
                if np.isfinite(check["before_mean_mm"]) and np.isfinite(check["after_mean_mm"]) and check["after_mean_mm"] > check["before_mean_mm"]:
                    self.log("WARNING: applying the field did not reduce T2-rigid to T1 surface distance on {}. Verify field sign/direction.".format(side))
            self.sideData[side].update(prepared[side])
        with open(os.path.join(self.outputDir, "surface_analysis_report.json"), "w", encoding="utf-8") as f: json.dump(report, f, indent=2)
        with open(os.path.join(self.outputDir, "local_patch_stats.json"), "w", encoding="utf-8") as f: json.dump(localPatchStats, f, indent=2)
        combinedPath = os.path.join(self.outputDir, "region_displacement_stats_all.csv")
        fieldnames = ["side","region","area_mm2","area_ratio_percent","valid_area_ratio_percent","mean_LR_mm","mean_AP_mm","mean_SI_mm","mean_magnitude_mm","p95_magnitude_mm"]
        with open(combinedPath, "w", newline="", encoding="utf-8-sig") as combinedFile:
            writer = csv.DictWriter(combinedFile, fieldnames=fieldnames); writer.writeheader()
            for side in ["left", "right"]:
                statsPath = os.path.join(self.outputDir, side + "_region_displacement_stats.csv")
                with open(statsPath, "r", newline="", encoding="utf-8-sig") as statsFile:
                    for row in csv.DictReader(statsFile): writer.writerow(row)
        self.onDirectionChanged(); self.onRegionVisibilityChanged(); slicer.util.resetThreeDViews()
        self.log("STEP 3 COMPLETE: LR/AP/SI heatmaps, T1-to-T2-rigid mapped surfaces, and directional patches are ready.")
        self.log("In the Slicer view, region fills are replaced by outlines to keep the displacement heatmap readable.")
        self.log("Direction values and patch display deformation are in mm; patch displacement is visually scaled by {:.3f}.".format(float(self.deformationScale.value)))
        self.startHtmlExport(3)

    def addAndSaveModel(self, poly, name, color, opacity, filename):
        node = self.logic.addModel(poly, name, color, opacity); self.generatedModelNodes.append(node)
        self.logic.savePolyData(poly, os.path.join(self.outputDir, filename)); return node

    def removeVisualizationNodes(self):
        prefixes = ("CBCTTMJ_Heatmap_", "CBCTTMJ_Patch_", "CBCTTMJ_Mapped_", "CBCTTMJ_RegionBoundary_")
        for node in list(slicer.util.getNodesByClass("vtkMRMLModelNode")):
            if node.GetName().startswith(prefixes): slicer.mrmlScene.RemoveNode(node)
        for node in list(slicer.util.getNodesByClass("vtkMRMLProceduralColorNode")):
            if node.GetName().startswith("CBCTTMJ_Color_"): slicer.mrmlScene.RemoveNode(node)
        self.generatedModelNodes = [n for n in self.generatedModelNodes if n and n.GetScene()]
        self.directionModels = {}; self.patchDirectionModels = {}

    def onSaveScene(self):
        out = os.path.abspath(self.outputEdit.text.strip()); os.makedirs(out, exist_ok=True)
        path = os.path.join(out, "CBCTTMJAnalysis_scene.mrb")
        try:
            if slicer.util.saveScene(path): self.log("Saved scene: " + path)
            else: slicer.util.errorDisplay("Slicer could not save scene.")
        except Exception as e: slicer.util.errorDisplay("Scene save failed:\n" + str(e))

    def removeGeneratedNodes(self):
        prefixes = ("CBCTTMJ_Model_", "CBCTTMJ_Axis_", "CBCTTMJ_Region_", "CBCTTMJ_Heatmap_", "CBCTTMJ_Patch_", "CBCTTMJ_Mapped_", "CBCTTMJ_RegionBoundary_")
        for node in list(slicer.util.getNodesByClass("vtkMRMLModelNode")):
            if node.GetName().startswith(prefixes): slicer.mrmlScene.RemoveNode(node)
        for node in list(slicer.util.getNodesByClass("vtkMRMLProceduralColorNode")):
            if node.GetName().startswith("CBCTTMJ_Color_"): slicer.mrmlScene.RemoveNode(node)
        self.generatedModelNodes = []; self.directionModels = {}; self.patchDirectionModels = {}; self.regionModels = {}; self.sideData = {}; self.stage2Ready = False

class CBCTTMJAnalysisLogic(ScriptedLoadableModuleLogic):
    def firstExistingPath(self, paths):
        for path in paths:
            if path and os.path.isfile(path): return path
        return None

    def maskToRASPolyData(self, binaryKJI, volumeNode):
        binary = np.asarray(binaryKJI, dtype=np.uint8)
        if binary.ndim != 3: raise ValueError("Mask must be a 3D KJI array.")
        k,j,i = binary.shape
        image = vtk.vtkImageData(); image.SetDimensions(i,j,k); image.SetOrigin(0,0,0); image.SetSpacing(1,1,1)
        scalars = numpy_to_vtk(np.ascontiguousarray(binary).ravel(order="C"), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR)
        scalars.SetName("Mask"); image.GetPointData().SetScalars(scalars)
        contour = vtk.vtkFlyingEdges3D(); contour.SetInputData(image); contour.SetValue(0,0.5); contour.ComputeNormalsOff(); contour.Update()
        ijkToRAS = vtk.vtkMatrix4x4(); volumeNode.GetIJKToRASMatrix(ijkToRAS)
        transform = vtk.vtkTransform(); transform.SetMatrix(ijkToRAS)
        tf = vtk.vtkTransformPolyDataFilter(); tf.SetInputConnection(contour.GetOutputPort()); tf.SetTransform(transform); tf.Update()
        clean = vtk.vtkCleanPolyData(); clean.SetInputConnection(tf.GetOutputPort()); clean.Update()
        tri = vtk.vtkTriangleFilter(); tri.SetInputConnection(clean.GetOutputPort()); tri.Update()
        out = vtk.vtkPolyData(); out.DeepCopy(tri.GetOutput()); return out

    def fossaComponents(self, volumeNode, labelValue):
        array = slicer.util.arrayFromVolume(volumeNode)
        # Match SimpleITK ConnectedComponent default face connectivity (6-neighbourhood).
        labels, n = ndimage.label(array == int(labelValue), structure=ndimage.generate_binary_structure(3, 1))
        if n == 0: return []
        sizes = np.bincount(labels.ravel())
        ids = sorted([i for i in range(1, len(sizes)) if sizes[i] > 0], key=lambda i: sizes[i], reverse=True)[:2]
        matrixV = vtk.vtkMatrix4x4(); volumeNode.GetIJKToRASMatrix(matrixV)
        mat = np.array([[matrixV.GetElement(r,c) for c in range(4)] for r in range(4)])
        result = []
        for idx in ids:
            coords = np.argwhere(labels == idx)
            meanIJK = np.array([coords[:,2].mean(), coords[:,1].mean(), coords[:,0].mean(), 1.0])
            center = (mat @ meanIJK)[:3]
            result.append({"component_id":int(idx), "mask":labels == idx, "size":int(sizes[idx]), "centerRAS":center})
        # RAS +X points to patient-right; patient-left therefore has the smaller RAS X.
        result.sort(key=lambda d: d["centerRAS"][0])
        return result

    def pcaAxesRAS(self, poly):
        points=vtk_to_numpy(poly.GetPoints().GetData()).astype(float); center=points.mean(axis=0); x=points-center
        vals,vecs=np.linalg.eigh(x.T@x); lr=vecs[:,np.argmax(vals)]; lr/=np.linalg.norm(lr)
        if np.dot(lr,[-1,0,0]) < 0: lr=-lr
        posterior=np.array([0.0,-1.0,0.0]); ap=posterior-np.dot(posterior,lr)*lr
        if np.linalg.norm(ap)<1e-8: raise ValueError("Cannot determine AP axis.")
        ap/=np.linalg.norm(ap); si=np.cross(lr,ap); si/=np.linalg.norm(si)
        if si[2]<0: ap=-ap; si=-si
        return {"origin":center,"LR":lr,"AP":ap,"SI":si}

    def extractUpperSurface(self, poly, si, threshold):
        """Use smoothed cell normals, neighbour voting, and small enclosed-patch repair.
        Selection is computed on a smoothed copy; output geometry comes from the original mesh.
        """
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        clean = vtk.vtkCleanPolyData(); clean.SetInputData(poly); clean.Update()
        tri = vtk.vtkTriangleFilter(); tri.SetInputConnection(clean.GetOutputPort()); tri.Update()
        original = vtk.vtkPolyData(); original.DeepCopy(tri.GetOutput())
        nCells = original.GetNumberOfCells()
        if nCells == 0: raise ValueError("Fossa surface contains no cells.")
        smooth = vtk.vtkSmoothPolyDataFilter(); smooth.SetInputData(original); smooth.SetNumberOfIterations(30); smooth.SetRelaxationFactor(0.05); smooth.FeatureEdgeSmoothingOff(); smooth.BoundarySmoothingOn(); smooth.Update()
        normals = vtk.vtkPolyDataNormals(); normals.SetInputConnection(smooth.GetOutputPort()); normals.ComputeCellNormalsOn(); normals.ComputePointNormalsOff(); normals.AutoOrientNormalsOn(); normals.ConsistencyOn(); normals.SplittingOff(); normals.Update()
        nArray = normals.GetOutput().GetCellData().GetNormals()
        if nArray is None or normals.GetOutput().GetNumberOfCells() != nCells: raise RuntimeError("Could not calculate consistent cell normals for upper-surface selection.")
        normalValues = vtk_to_numpy(nArray).astype(np.float64)
        selected = (normalValues @ np.asarray(si, dtype=np.float64)) >= float(threshold)
        raw = vtk_to_numpy(original.GetPolys().GetData())
        faces = raw.reshape(-1,4)[:,1:].astype(np.int64)
        if len(faces) != nCells: raise RuntimeError("Expected a triangulated fossa mesh.")
        edges = np.concatenate([faces[:,[0,1]], faces[:,[1,2]], faces[:,[2,0]]], axis=0)
        owners = np.tile(np.arange(nCells), 3)
        edges = np.sort(edges, axis=1)
        _, inverse, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
        order = np.argsort(inverse); starts = np.r_[0, np.cumsum(counts)[:-1]]
        rows, cols = [], []
        for st, count in zip(starts, counts):
            if count == 2:
                a, b = owners[order[st:st+2]]
                rows.extend([a,b]); cols.extend([b,a])
        graph = coo_matrix((np.ones(len(rows), dtype=np.uint8), (rows, cols)), shape=(nCells,nCells)).tocsr()
        graph.data[:] = 1
        degree = np.diff(graph.indptr)
        for _ in range(5):
            neighbourCount = np.asarray(graph @ selected.astype(np.int32)).ravel()
            fill = (~selected) & (degree >= 2) & (neighbourCount >= np.ceil(degree * 0.65))
            if not np.any(fill): break
            selected |= fill
        backgroundIds = np.flatnonzero(~selected)
        if len(backgroundIds):
            subgraph = graph[backgroundIds][:, backgroundIds]
            nComp, labels = connected_components(subgraph, directed=False)
            pts = vtk_to_numpy(original.GetPoints().GetData()).astype(np.float64)
            triangles = pts[faces]
            areas = 0.5 * np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0]), axis=1)
            totalSelectedArea = float(areas[selected].sum())
            maxFillArea = totalSelectedArea * 0.015
            for label in range(nComp):
                ids = backgroundIds[labels == label]
                if areas[ids].sum() > maxFillArea: continue
                adjacent = np.unique(graph[ids].indices)
                if len(adjacent) == 0: continue
                if np.all(degree[ids] >= 3) and np.any(selected[adjacent]): selected[ids] = True
        selectedIds = np.flatnonzero(selected)
        if len(selectedIds) == 0: raise ValueError("No upper-surface cells selected; lower the normal threshold.")
        idList = vtk.vtkIdList()
        for cid in selectedIds: idList.InsertNextId(int(cid))
        extract = vtk.vtkExtractCells(); extract.SetInputData(original); extract.SetCellList(idList); extract.Update()
        geom = vtk.vtkGeometryFilter(); geom.SetInputConnection(extract.GetOutputPort()); geom.Update()
        clean2 = vtk.vtkCleanPolyData(); clean2.SetInputConnection(geom.GetOutputPort()); clean2.Update()
        conn = vtk.vtkPolyDataConnectivityFilter(); conn.SetInputConnection(clean2.GetOutputPort()); conn.SetExtractionModeToLargestRegion(); conn.Update()
        tri2 = vtk.vtkTriangleFilter(); tri2.SetInputConnection(conn.GetOutputPort()); tri2.Update()
        out = vtk.vtkPolyData(); out.DeepCopy(tri2.GetOutput())
        self._lastUpperSurfaceCellCount = int(len(selectedIds))
        return out

    def splitRegions(self, poly, axes):
        """Split by the LR=0 and AP=0 lines through the area-weighted surface centroid.
        Areas are not forced to be equal; region order matches stage1.py.
        """
        triFilter = vtk.vtkTriangleFilter(); triFilter.SetInputData(poly); triFilter.Update()
        mesh = vtk.vtkPolyData(); mesh.DeepCopy(triFilter.GetOutput())
        faces = self.triangles(mesh)
        pts = vtk_to_numpy(mesh.GetPoints().GetData()).astype(np.float64)
        tri = pts[faces]; centers = tri.mean(axis=1)
        areas = 0.5 * np.linalg.norm(np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0]), axis=1)
        total = float(areas.sum())
        if total <= 0: raise ValueError("Invalid upper-surface area.")
        lr = np.asarray(axes["LR"], dtype=np.float64); lr /= np.linalg.norm(lr)
        ap = np.asarray(axes["AP"], dtype=np.float64); ap = ap - np.dot(ap,lr)*lr; ap /= np.linalg.norm(ap)
        centroid = np.average(centers, axis=0, weights=areas)
        rel = centers - centroid; lrValues = rel @ lr; apValues = rel @ ap
        masks = [(lrValues < 0) & (apValues >= 0), (lrValues >= 0) & (apValues >= 0), (lrValues < 0) & (apValues < 0), (lrValues >= 0) & (apValues < 0)]
        outputs = []
        for mask in masks:
            ids = np.flatnonzero(mask)
            if len(ids) == 0:
                outputs.append({"poly":vtk.vtkPolyData(), "area_mm2":0.0, "area_ratio_percent":0.0}); continue
            idList = vtk.vtkIdList()
            for cid in ids: idList.InsertNextId(int(cid))
            extract = vtk.vtkExtractCells(); extract.SetInputData(mesh); extract.SetCellList(idList); extract.Update()
            geom = vtk.vtkGeometryFilter(); geom.SetInputConnection(extract.GetOutputPort()); geom.Update()
            clean = vtk.vtkCleanPolyData(); clean.SetInputConnection(geom.GetOutputPort()); clean.Update()
            triOut = vtk.vtkTriangleFilter(); triOut.SetInputConnection(clean.GetOutputPort()); triOut.Update()
            region = vtk.vtkPolyData(); region.DeepCopy(triOut.GetOutput())
            area = float(areas[mask].sum())
            outputs.append({"poly":region, "area_mm2":area, "area_ratio_percent":100.0*area/total})
        return outputs

    def makeAxisArrow(self, origin, direction, length):
        origin=np.asarray(origin,float); direction=np.asarray(direction,float); direction/=np.linalg.norm(direction); end=origin+direction*length
        line=vtk.vtkLineSource(); line.SetPoint1(origin); line.SetPoint2(end)
        tube=vtk.vtkTubeFilter(); tube.SetInputConnection(line.GetOutputPort()); tube.SetRadius(0.25); tube.SetNumberOfSides(12); tube.CappingOn(); tube.Update()
        cone=vtk.vtkConeSource(); cone.SetCenter(end-direction*1.5); cone.SetDirection(direction); cone.SetHeight(3.0); cone.SetRadius(0.85); cone.SetResolution(20); cone.Update()
        app=vtk.vtkAppendPolyData(); app.AddInputConnection(tube.GetOutputPort()); app.AddInputConnection(cone.GetOutputPort()); app.Update()
        clean=vtk.vtkCleanPolyData(); clean.SetInputConnection(app.GetOutputPort()); clean.Update(); out=vtk.vtkPolyData(); out.DeepCopy(clean.GetOutput()); return out

    def addModel(self, poly, name, color, opacity):
        node=slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode",name); node.SetAndObservePolyData(poly); node.CreateDefaultDisplayNodes()
        d=node.GetDisplayNode(); d.SetColor(*color); d.SetOpacity(float(opacity)); d.SetVisibility(True); return node

    def savePolyData(self, poly, path):
        writer=vtk.vtkXMLPolyDataWriter(); writer.SetFileName(path); writer.SetInputData(poly); writer.SetDataModeToBinary()
        if writer.Write()!=1: raise IOError("Failed writing " + path)

    def copyPolyWithPoints(self, poly, points):
        points = np.asarray(points, dtype=np.float64)
        if points.shape != (poly.GetNumberOfPoints(), 3): raise ValueError("New point array shape does not match polydata.")
        out = vtk.vtkPolyData(); out.DeepCopy(poly)
        vtkPoints = vtk.vtkPoints(); vtkPoints.SetData(numpy_to_vtk(points, deep=True, array_type=vtk.VTK_DOUBLE)); out.SetPoints(vtkPoints)
        return out

    def polyDataWithScalars(self, poly, name, values):
        out=vtk.vtkPolyData(); out.DeepCopy(poly); v=np.asarray(values,dtype=np.float32)
        if len(v)!=out.GetNumberOfPoints(): raise ValueError("Scalar count does not match points.")
        v=np.nan_to_num(v,nan=0.0,posinf=0.0,neginf=0.0); arr=numpy_to_vtk(v,deep=True,array_type=vtk.VTK_FLOAT); arr.SetName(name); out.GetPointData().AddArray(arr); out.GetPointData().SetActiveScalars(name); return out

    def addScalarModel(self, poly, name, scalarName, vmax, opacity):
        node=self.addModel(poly,name,(1,1,1),opacity); d=node.GetDisplayNode()
        color=slicer.mrmlScene.GetFirstNodeByName("CBCTTMJ_Color_BlueWhiteRed")
        if color is None: color=slicer.mrmlScene.AddNewNodeByClass("vtkMRMLProceduralColorNode","CBCTTMJ_Color_BlueWhiteRed")
        ctf=color.GetColorTransferFunction(); ctf.RemoveAllPoints(); v=max(float(vmax),1e-6)
        ctf.AddRGBPoint(-v,0.18,0.32,0.75); ctf.AddRGBPoint(-0.5*v,0.55,0.68,0.88); ctf.AddRGBPoint(0,1,1,1); ctf.AddRGBPoint(0.5*v,0.90,0.55,0.48); ctf.AddRGBPoint(v,0.72,0.08,0.12)
        d.SetAndObserveColorNodeID(color.GetID()); d.SetScalarVisibility(True); d.SetActiveScalarName(scalarName)
        if hasattr(d,"SetScalarModeToUsePointFieldData"): d.SetScalarModeToUsePointFieldData()
        if hasattr(d,"SetScalarRangeFlag"): d.SetScalarRangeFlag(1)
        if hasattr(d,"SetScalarRange"): d.SetScalarRange(-v,v)
        return node

    def sampleField(self, points, field, affine):
        pts=np.asarray(points,dtype=float); inv=np.linalg.inv(affine); ijk=(inv@np.column_stack([pts,np.ones(len(pts))]).T).T[:,:3]
        shape=np.asarray(field.shape[:3]); valid=np.all((ijk>=0)&(ijk<=shape[None,:]-1),axis=1); out=np.full((len(pts),3),np.nan)
        ids=np.flatnonzero(valid)
        if len(ids):
            coords=ijk[ids].T
            for c in range(3): out[ids,c]=map_coordinates(field[...,c],coords,order=1,mode="nearest",prefilter=False)
            bad=~np.all(np.isfinite(out[ids]),axis=1); valid[ids[bad]]=False; out[ids[bad]]=np.nan
        return out,valid

    def inverseDisplacement(self, y, field, affine, maxIterations=50, tolerance=1e-3):
        y=np.asarray(y,dtype=float); x=y.copy(); valid=np.ones(len(y),dtype=bool); maxUpdate=np.inf; used=0
        # Treat field as T2-rigid -> T1: y=x+u(x), solve x approximately for each T1 point y.
        for it in range(maxIterations):
            u,ok=self.sampleField(x,field,affine); valid &= ok; ids=np.flatnonzero(valid)
            if not len(ids): break
            xn=x.copy(); xn[ids]=y[ids]-u[ids]; delta=np.linalg.norm(xn[ids]-x[ids],axis=1); maxUpdate=float(delta.max()) if len(delta) else 0.0
            x=xn; used=it+1
            if maxUpdate<tolerance: break
        disp=x-y; disp[~valid]=np.nan
        return disp,valid,{"iterations":used,"last_max_update_mm":float(maxUpdate) if np.isfinite(maxUpdate) else None,"converged_to_tolerance":bool(np.isfinite(maxUpdate) and maxUpdate<tolerance)}

    def makePatch(self, upper, axes, field, affine, resolution, offset):
        pts = vtk_to_numpy(upper.GetPoints().GetData()).astype(np.float64)
        center = pts.mean(axis=0); rel = pts - center
        u = rel @ axes["LR"]; v = rel @ axes["AP"]
        du = max(float(u.max()-u.min()), 1e-3); dv = max(float(v.max()-v.min()), 1e-3)
        u0, u1 = float(u.min()-0.05*du), float(u.max()+0.05*du)
        v0, v1 = float(v.min()-0.05*dv), float(v.max()+0.05*dv)
        U, V = np.meshgrid(np.linspace(u0,u1,resolution), np.linspace(v0,v1,resolution), indexing="xy")
        points = (center + U[...,None]*axes["LR"] + V[...,None]*axes["AP"] + float(offset)*axes["SI"]).reshape(-1,3)
        poly = vtk.vtkPolyData(); vp = vtk.vtkPoints(); vp.SetData(numpy_to_vtk(points.astype(np.float64), deep=True, array_type=vtk.VTK_DOUBLE)); poly.SetPoints(vp)
        cells = vtk.vtkCellArray(); nu = U.shape[1]; nv = U.shape[0]
        for j in range(nv-1):
            for i in range(nu-1):
                ids = [j*nu+i, j*nu+i+1, (j+1)*nu+i+1, (j+1)*nu+i]
                q = vtk.vtkQuad()
                for z, idx in enumerate(ids): q.GetPointIds().SetId(z, int(idx))
                cells.InsertNextCell(q)
        poly.SetPolys(cells)
        disp, valid, info = self.inverseDisplacement(points, field, affine)
        comps = {k:disp @ axes[k] for k in ["LR", "AP", "SI"]}
        comps["MAG"] = np.linalg.norm(disp, axis=1)
        return poly, disp, valid, comps

    def deformPatch(self, base, disp, valid, component, axis, mode, scale):
        pts=vtk_to_numpy(base.GetPoints().GetData()).astype(float); comp=np.asarray(component); good=np.asarray(valid)&np.isfinite(comp)
        delta=np.zeros_like(pts); delta[good]=float(scale)*comp[good,None]*np.asarray(axis)[None,:]
        out=vtk.vtkPolyData(); out.DeepCopy(base); vp=vtk.vtkPoints(); vp.SetData(numpy_to_vtk((pts+delta).astype(np.float64),deep=True)); out.SetPoints(vp)
        vals=numpy_to_vtk(np.nan_to_num(comp,nan=0.0).astype(np.float32),deep=True,array_type=vtk.VTK_FLOAT); vals.SetName("U_{}_mm".format(mode)); out.GetPointData().AddArray(vals); out.GetPointData().SetActiveScalars(vals.GetName())
        return out

    def symmetricRange(self, arrays):
        vals=[]
        for a in arrays:
            a=np.asarray(a,dtype=float); a=a[np.isfinite(a)]
            if len(a): vals.append(np.abs(a))
        return max(float(np.percentile(np.concatenate(vals),99)),1e-4) if vals else 1.0

    def triangles(self, poly):
        raw=vtk_to_numpy(poly.GetPolys().GetData())
        if len(raw)%4: raise ValueError("Expected triangulated polydata.")
        return raw.reshape(-1,4)[:,1:].astype(int)

    def writeRegionStats(self, side, poly, disp, valid, axes, path):
        pts=vtk_to_numpy(poly.GetPoints().GetData()).astype(float); faces=self.triangles(poly); tri=pts[faces]; centers=tri.mean(axis=1)
        area=0.5*np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1); total=area.sum()
        centroid=np.average(centers,axis=0,weights=np.maximum(area,1e-12)); rel=centers-centroid; lr=rel@axes["LR"]; ap=rel@axes["AP"]
        masks=[("Right-Posterior",(lr<0)&(ap>=0)),("Left-Posterior",(lr>=0)&(ap>=0)),("Right-Anterior",(lr<0)&(ap<0)),("Left-Anterior",(lr>=0)&(ap<0))]
        faceValid=np.all(valid[faces],axis=1)&np.all(np.isfinite(disp[faces]),axis=(1,2)); cellDisp=np.nanmean(disp[faces],axis=1)
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=["side","region","area_mm2","area_ratio_percent","valid_area_ratio_percent","mean_LR_mm","mean_AP_mm","mean_SI_mm","mean_magnitude_mm","p95_magnitude_mm"]); w.writeheader()
            for name,mask in masks:
                ids=np.flatnonzero(mask); a=float(area[ids].sum()) if len(ids) else 0; good=ids[faceValid[ids]] if len(ids) else np.array([],dtype=int); ga=float(area[good].sum()) if len(good) else 0
                if len(good):
                    vec=np.average(cellDisp[good],axis=0,weights=area[good]); comps=[float(vec@axes[k]) for k in ["LR","AP","SI"]]; mag=np.linalg.norm(cellDisp[good],axis=1); meanMag=float(np.average(mag,weights=area[good])); p95=float(np.percentile(mag,95))
                else: comps=[float("nan")]*3; meanMag=float("nan"); p95=float("nan")
                w.writerow({"side":side,"region":name,"area_mm2":a,"area_ratio_percent":100*a/total if total else 0,"valid_area_ratio_percent":100*ga/a if a else 0,"mean_LR_mm":comps[0],"mean_AP_mm":comps[1],"mean_SI_mm":comps[2],"mean_magnitude_mm":meanMag,"p95_magnitude_mm":p95})

    def meanDistance(self, points, target):
        implicit=vtk.vtkImplicitPolyDataDistance(); implicit.SetInput(target); step=max(1,len(points)//20000)
        vals=[abs(float(implicit.EvaluateFunction(p))) for p in points[::step]]
        return float(np.mean(vals)) if vals else float("nan")

    def fieldDirectionCheck(self, t1Upper, t2Upper, field, affine):
        t1p=vtk_to_numpy(t1Upper.GetPoints().GetData()).astype(float); t2p=vtk_to_numpy(t2Upper.GetPoints().GetData()).astype(float)
        before=self.meanDistance(t2p,t1Upper); u,valid=self.sampleField(t2p,field,affine); good=valid&np.all(np.isfinite(u),axis=1)
        after=self.meanDistance(t2p[good]+u[good],t1Upper) if np.any(good) else float("nan")
        return {"before_mean_mm":before,"after_mean_mm":after}


class CBCTTMJAnalysisTest(ScriptedLoadableModuleTest):
    """Lightweight module smoke test for Slicer's Reload and Test action."""

    def runTest(self):
        modulePath = slicer.util.modulePath("CBCTTMJAnalysis")
        self.assertTrue(modulePath and os.path.isfile(modulePath),
                        "CBCTTMJAnalysis module file was not found.")
        backendPath = os.path.join(os.path.dirname(modulePath),
                                   "CBCTTMJAnalysisLib", "registration_backend.py")
        self.assertTrue(os.path.isfile(backendPath),
                        "ANTsPy registration backend was not found: " + backendPath)
        self.delayDisplay("CBCT TMJ Analysis smoke test passed. Backend file exists; registration was not run.")
