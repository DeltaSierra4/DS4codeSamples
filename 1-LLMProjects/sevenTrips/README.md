## Setup Instructions

### 1. Install uv package manager

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Install Python dependencies

```bash
uv venv
uv pip install -r requirements.txt
```


### 3. Install Tesseract OCR (64-bit Windows)

Download and install Tesseract 64-bit from:
https://github.com/UB-Mannheim/tesseract/wiki

**Recommended installation path:**
```
C:\Program Files\Tesseract-OCR\tesseract.exe
```

The application automatically detects Tesseract at standard Windows 64-bit installation paths.
#### Add Tesseract to PATH (Windows)

If Tesseract isn't detected, add its folder to your PATH:

- GUI
	1. Press Win+R, type `sysdm.cpl`, press Enter.
	2. Go to the Advanced tab → Environment Variables…
	3. Under System variables (or User variables), select `Path` → Edit…
	4. Click New and add: `C:\Program Files\Tesseract-OCR`
	5. Save all dialogs and reopen your terminal.

- PowerShell (User PATH)

```powershell
# Adds Tesseract to the current user's PATH (no admin required)
[Environment]::SetEnvironmentVariable('Path', "$env:Path;C:\Program Files\Tesseract-OCR", 'User')
```

- PowerShell (System PATH – requires Administrator PowerShell)

```powershell
setx /M PATH "$($Env:PATH);C:\Program Files\Tesseract-OCR"
```

Verify:

```powershell
# Open a new terminal first
tesseract --version
```

### 4. Activate environment and run

## Usage
```bash
.venv\Scripts\activate
uv run python main.py path/to/your_resume path/to/job_description_file
```

Follow the prompts once the script runs. First, you will be asked to provide the role that you're applying for, then you will need to select one out of four options on how much revision you want to perform (1 for basic, 2 for standard, 3 for comprehensive, and 4 for a combination of all three variants).