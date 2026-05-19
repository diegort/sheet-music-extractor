# Sheet Music Extractor

Extract and crop sheet music pages from PDFs, optimized for Kindle and other e-reader devices.

## Features

- Load multi-page PDF scores
- Navigate pages
- Rotate pages
- Crop regions
- Export cropped pages as high-quality PDF
- Built-in Kindle device profiles (PW 7th gen 6", PW 11+ gen 7")
- Create custom device profiles (screen size + resolution)
- Settings and custom profiles persist between sessions

## Requirements

- Python 3.10+
- Tkinter (included with most Python installations)

## Setup

```bash
pip install -r requirements.txt
python extractor.py
```

## Usage

1. Click **Cargar PDF Completo** to open a PDF
2. Select a device profile from the dropdown (or click **+** to add a custom one)
3. Navigate pages with **◀ Ant / Sig ▶** buttons or arrow keys
4. Optionally drag a crop rectangle on the preview
5. Click **💾 Guardar Página Actual Cortada** to export

## Building Windows Executable

Push a version tag to trigger the GitHub Actions build:

```bash
git tag v1.0
git push --tags
```

The `.exe` will be available in the GitHub Releases page.

## License

MIT
