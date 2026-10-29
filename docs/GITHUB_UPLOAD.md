# Upload CBCTTMJAnalysis to GitHub (Windows)

## Before uploading

- Review `.gitignore` and run `git status` before committing.
- Do not upload patient CBCT scans, masks, DICOM, segmentation files, deformation fields, screenshots with identifiable information, or patient-specific HTML.
- Do not commit credentials, tokens, local environment files, or private paths containing sensitive information.
- Keep the repository private until you have reviewed data privacy, third-party licenses, and whether you are allowed to publish the source.
- No open-source license is included. Choose a license only after confirming ownership and third-party terms.

## Create the repository

1. Sign in to GitHub and create an empty repository named `CBCTTMJAnalysis`.
2. Do not initialize the remote repository with a README, license, or `.gitignore`, because this package already includes a README and `.gitignore`.
3. Extract this package and open PowerShell in the folder containing `CBCTTMJAnalysis.py` and `README.md`.

## Initial push

```powershell
git init
git add .
git status
```

Inspect the staged files. If anything sensitive is staged, remove it before continuing. Then run:

```powershell
git commit -m "Initial commit: CBCT TMJ Analysis"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/CBCTTMJAnalysis.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username. Use Git Credential Manager or GitHub's supported authentication flow. Do not paste access tokens into source files or chat.

## Subsequent updates

```powershell
git add .
git status
git commit -m "Describe the change"
git push
```

## What the automated check covers

The included GitHub Actions workflow compiles Python source files for syntax. It does not install the native ANTsPy/ITK/VTK stack and does not run Slicer, registration, displacement-field validation, or browser interaction tests. Run `verify_backend.py` in the external Python 3.10 environment and test the complete workflow in Slicer separately.
