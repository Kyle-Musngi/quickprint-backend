import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import pypdf
from PIL import Image

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB

SUPPORTED_EXTENSIONS = {
    'pdf': ['.pdf'],
    'docx': ['.docx'],
    'doc': ['.doc'],
    'pptx': ['.pptx'],
    'ppt': ['.ppt'],
    'rtf': ['.rtf'],
    'txt': ['.txt'],
    'image': ['.jpg', '.jpeg', '.png'],
}

CACHE_DIR = os.path.join(tempfile.gettempdir(), 'uqp_doc_cache')
os.makedirs(CACHE_DIR, exist_ok=True)


class DocumentInspectionError(Exception):
    pass


def find_soffice_executable():
    """
    Search for LibreOffice headless binary on system.
    """
    cmd = shutil.which("soffice") or shutil.which("libreoffice")
    if cmd:
        return cmd
    common_windows_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for p in common_windows_paths:
        if os.path.exists(p):
            return p
    return None


def has_word_com_engine():
    """
    Check if Microsoft Word COM automation is available on Windows.
    """
    if os.name != 'nt':
        return False
    try:
        ps_cmd = "$w = New-Object -ComObject Word.Application; $v = $w.Version; $w.Quit(); Write-Output $v"
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=8
        )
        return res.returncode == 0 and bool(res.stdout.strip())
    except Exception:
        return False


def has_powerpoint_com_engine():
    """
    Check if Microsoft PowerPoint COM automation is available on Windows.
    """
    if os.name != 'nt':
        return False
    try:
        ps_cmd = "$p = New-Object -ComObject PowerPoint.Application; $v = $p.Version; $p.Quit(); Write-Output $v"
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=8
        )
        return res.returncode == 0 and bool(res.stdout.strip())
    except Exception:
        return False


def detect_file_type_and_signature(file_obj, filename=""):
    """
    Inspect magic bytes / headers to determine document format.
    Does not rely on extension alone.
    """
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    file_obj.seek(0)
    header = file_obj.read(8192)
    file_obj.seek(pos)

    if not header:
        return None

    # Check for PDF (%PDF-)
    if header.startswith(b'%PDF-') or b'%PDF-' in header[:1024]:
        return 'pdf'

    # Check for ZIP based formats (DOCX, PPTX)
    if header.startswith(b'PK\x03\x04'):
        file_obj.seek(0)
        try:
            if zipfile.is_zipfile(file_obj):
                with zipfile.ZipFile(file_obj, 'r') as z:
                    names = [n.lower() for n in z.namelist()]
                    if any('word/document.xml' in n for n in names):
                        return 'docx'
                    if any('ppt/presentation.xml' in n for n in names):
                        return 'pptx'
        except Exception:
            pass
        finally:
            file_obj.seek(pos)

    # Check for legacy OLE2 (DOC, PPT)
    if header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
        ext = os.path.splitext(filename)[1].lower() if filename else ""
        if ext in ['.ppt']:
            return 'ppt'
        return 'doc'

    # Check for RTF
    if header.startswith(b'{\\rtf'):
        return 'rtf'

    # Check for Images (JPEG, PNG)
    if header.startswith(b'\xFF\xD8\xFF'):
        return 'image'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image'

    # Check for plain text
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    if ext == '.txt':
        try:
            header.decode('utf-8')
            return 'txt'
        except UnicodeDecodeError:
            try:
                header.decode('latin-1')
                return 'txt'
            except Exception:
                pass

    return None


def inspect_pdf_pages(file_obj):
    """
    Uses pypdf to accurately count pages in PDF.
    Validates encryption and corrupt file structures.
    """
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    file_obj.seek(0)
    try:
        reader = pypdf.PdfReader(file_obj)
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt('')
                if decrypted == pypdf.PasswordType.NOT_DECRYPTED:
                    raise DocumentInspectionError(
                        "This PDF document is password-protected or encrypted. Please remove password protection and re-upload."
                    )
            except Exception:
                raise DocumentInspectionError(
                    "This PDF document is password-protected or encrypted. Please remove password protection and re-upload."
                )

        pages = len(reader.pages)
        if pages <= 0:
            raise DocumentInspectionError("The PDF document does not contain any printable pages.")
        return pages
    except DocumentInspectionError:
        raise
    except Exception as e:
        raise DocumentInspectionError(f"Corrupt or unreadable PDF document: {str(e)}")
    finally:
        try:
            file_obj.seek(pos)
        except Exception:
            pass


def inspect_image_pages(file_obj):
    """
    Validates image file using Pillow and returns 1 page.
    """
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    file_obj.seek(0)
    try:
        with Image.open(file_obj) as img:
            img.verify()
        return 1
    except Exception as e:
        raise DocumentInspectionError(f"Corrupt or unreadable image file: {str(e)}")
    finally:
        try:
            file_obj.seek(pos)
        except Exception:
            pass


def convert_word_with_libreoffice(input_path, output_dir):
    """
    Convert Word/RTF/TXT to PDF using headless LibreOffice.
    """
    soffice_bin = find_soffice_executable()
    if not soffice_bin:
        return None

    cmd = [
        soffice_bin,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        input_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if res.returncode == 0:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
            if os.path.exists(pdf_path):
                return pdf_path
    except Exception:
        pass
    return None


def convert_word_with_word_com(input_path, output_pdf_path):
    """
    Convert DOCX, DOC, RTF, or TXT to PDF using native Word COM automation on Windows.
    """
    if os.name != 'nt':
        return None

    norm_in = os.path.abspath(input_path).replace("'", "''")
    norm_out = os.path.abspath(output_pdf_path).replace("'", "''")

    ps_script = f"""
$ErrorActionPreference = 'Stop'
$w = $null
$d = $null
try {{
    $w = New-Object -ComObject Word.Application
    $w.Visible = $false
    $w.DisplayAlerts = 0
    $d = $w.Documents.Open('{norm_in}', [ref]$false, [ref]$true)
    $d.ExportAsFixedFormat('{norm_out}', 17) # 17 = wdExportFormatPDF
    $pages = $d.ComputeStatistics(2) # 2 = wdStatisticPages
    $d.Close([ref]$false)
    $w.Quit()
    Write-Output $pages
}} catch {{
    if ($d) {{ try {{ $d.Close([ref]$false) }} catch {{}} }}
    if ($w) {{ try {{ $w.Quit() }} catch {{}} }}
    Write-Error $_.Exception.Message
    exit 1
}}
"""
    try:
        encoded = base64.b64encode(ps_script.encode('utf-16le')).decode('ascii')
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=30
        )
        if res.returncode == 0 and os.path.exists(output_pdf_path):
            return output_pdf_path
    except Exception:
        pass
    return None


def convert_presentation_with_powerpoint_com(input_path, output_pdf_path):
    """
    Convert PPTX or PPT to PDF and count slides using native PowerPoint COM automation.
    """
    if os.name != 'nt':
        return None

    norm_in = os.path.abspath(input_path).replace("'", "''")
    norm_out = os.path.abspath(output_pdf_path).replace("'", "''")

    ps_script = f"""
$ErrorActionPreference = 'Stop'
$ppt = $null
$pres = $null
try {{
    $ppt = New-Object -ComObject PowerPoint.Application
    $pres = $ppt.Presentations.Open('{norm_in}', [Microsoft.Office.Core.MsoTriState]::msoTrue, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    $pres.SaveAs('{norm_out}', 32) # 32 = ppSaveAsPDF
    $slides = $pres.Slides.Count
    $pres.Close()
    $ppt.Quit()
    Write-Output $slides
}} catch {{
    if ($pres) {{ try {{ $pres.Close() }} catch {{}} }}
    if ($ppt) {{ try {{ $ppt.Quit() }} catch {{}} }}
    Write-Error $_.Exception.Message
    exit 1
}}
"""
    try:
        encoded = base64.b64encode(ps_script.encode('utf-16le')).decode('ascii')
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=30
        )
        if res.returncode == 0 and os.path.exists(output_pdf_path):
            return output_pdf_path
    except Exception:
        pass
    return None


def render_and_count_document_pages(file_obj, filename, doc_type, sha256_hash):
    """
    Converts Word, RTF, TXT, or PPT documents to PDF using available rendering engines
    (LibreOffice, native Microsoft Word COM, or native PowerPoint COM).
    Caches the rendered PDF and page count to guarantee fast response times on reuse.
    """
    # 1. Check cache first
    meta_cache_path = os.path.join(CACHE_DIR, f"{sha256_hash}.json")
    pdf_cache_path = os.path.join(CACHE_DIR, f"{sha256_hash}.pdf")

    if os.path.exists(meta_cache_path) and os.path.exists(pdf_cache_path):
        try:
            with open(meta_cache_path, 'r', encoding='utf-8') as f_meta:
                cached = json.load(f_meta)
                if cached.get('page_count') and cached.get('page_count') > 0:
                    return cached['page_count']
        except Exception:
            pass

    # Read binary content
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    file_obj.seek(0)
    content = file_obj.read()
    file_obj.seek(pos)

    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        ext = f".{doc_type}"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_input = os.path.join(temp_dir, f"source{ext}")
        with open(temp_input, 'wb') as f_out:
            f_out.write(content)

        rendered_pdf = None

        # Try LibreOffice first
        rendered_pdf = convert_word_with_libreoffice(temp_input, temp_dir)

        # If not converted and Word format / RTF / TXT, try Word COM
        if not rendered_pdf and doc_type in ['docx', 'doc', 'rtf', 'txt']:
            temp_pdf_target = os.path.join(temp_dir, "rendered.pdf")
            rendered_pdf = convert_word_with_word_com(temp_input, temp_pdf_target)

        # If PPTX / PPT, try PowerPoint COM
        if not rendered_pdf and doc_type in ['pptx', 'ppt']:
            temp_pdf_target = os.path.join(temp_dir, "rendered.pdf")
            rendered_pdf = convert_presentation_with_powerpoint_com(temp_input, temp_pdf_target)

        if not rendered_pdf or not os.path.exists(rendered_pdf):
            raise DocumentInspectionError(
                f"Automatic rendered page counting for Word documents (.{doc_type}) requires a document-rendering engine (such as LibreOffice or Microsoft Word), "
                "which is not currently available. To ensure 100% accurate page count and pricing, please save or export your document as a PDF (.pdf) and upload the PDF instead."
            )

        # Count pages in the rendered PDF
        with open(rendered_pdf, 'rb') as pdf_file:
            pages = inspect_pdf_pages(pdf_file)

        # Cache the resulting PDF and metadata
        try:
            shutil.copy2(rendered_pdf, pdf_cache_path)
            with open(meta_cache_path, 'w', encoding='utf-8') as f_meta:
                json.dump({
                    "sha256": sha256_hash,
                    "filename": filename,
                    "doc_type": doc_type,
                    "page_count": pages
                }, f_meta)
        except Exception:
            pass

        return pages


def parse_and_validate_page_range(range_str: str, total_pages: int):
    """
    Parses and validates custom page range string like "1-3, 5, 7-9".
    Returns (list_of_pages, effective_page_count).
    """
    if not range_str or range_str.strip().lower() in ['all', '']:
        return list(range(1, total_pages + 1)), total_pages

    cleaned = range_str.strip()
    parts = cleaned.split(',')
    selected_pages = set()

    for part in parts:
        item = part.strip()
        if not item:
            continue
        if '-' in item:
            sub = item.split('-')
            if len(sub) != 2:
                raise DocumentInspectionError(f"Invalid page range format: '{item}'")
            try:
                start = int(sub[0].strip())
                end = int(sub[1].strip())
            except ValueError:
                raise DocumentInspectionError(f"Page range values must be integers: '{item}'")

            if start < 1 or end > total_pages or start > end:
                raise DocumentInspectionError(
                    f"Page range '{item}' is out of document bounds (document has {total_pages} page(s))."
                )
            for p in range(start, end + 1):
                selected_pages.add(p)
        else:
            try:
                page_num = int(item)
            except ValueError:
                raise DocumentInspectionError(f"Invalid page number: '{item}'")

            if page_num < 1 or page_num > total_pages:
                raise DocumentInspectionError(
                    f"Page number {page_num} is out of document bounds (document has {total_pages} page(s))."
                )
            selected_pages.add(page_num)

    if not selected_pages:
        raise DocumentInspectionError("No valid pages selected in the specified range.")

    sorted_pages = sorted(list(selected_pages))
    return sorted_pages, len(sorted_pages)


def validate_and_inspect_document(file_obj, filename=""):
    """
    Comprehensive document validation and page counting.
    - Validates file size > 0 and <= MAX_UPLOAD_SIZE.
    - Inspects magic bytes (does not trust extension alone).
    - Accurately counts pages via pypdf (for PDF), Pillow (for images),
      or headless document conversion (for Word, PPT, RTF, TXT).
    - Returns structured metadata dictionary.
    """
    # 1. Check size
    file_size = getattr(file_obj, 'size', None)
    if file_size is None:
        pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
        file_obj.seek(0, os.SEEK_END)
        file_size = file_obj.tell()
        file_obj.seek(pos)

    if file_size <= 0:
        raise DocumentInspectionError("The uploaded file is empty (0 bytes). Please upload a valid document.")

    if file_size > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
        raise DocumentInspectionError(
            f"File size ({file_size / (1024*1024):.1f} MB) exceeds the maximum allowed upload limit of {max_mb} MB."
        )

    # 2. Compute SHA-256 for caching & integrity
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    file_obj.seek(0)
    hasher = hashlib.sha256()
    while True:
        chunk = file_obj.read(65536)
        if not chunk:
            break
        hasher.update(chunk)
    sha256_hash = hasher.hexdigest()
    file_obj.seek(pos)

    # 3. Inspect format signature
    doc_type = detect_file_type_and_signature(file_obj, filename)
    if not doc_type:
        ext = os.path.splitext(filename)[1].lower() if filename else ""
        all_supported = [e for exts in SUPPORTED_EXTENSIONS.values() for e in exts]
        if ext in all_supported:
            raise DocumentInspectionError(
                f"File content does not match its '{ext}' extension or the file is corrupted. "
                "Please verify the file and try again."
            )
        else:
            raise DocumentInspectionError(
                f"Unsupported document format '{ext or 'unknown'}'. "
                "Supported formats are PDF (.pdf), Word (.docx, .doc), PowerPoint (.pptx, .ppt), RTF, TXT, and Images (.jpg, .png)."
            )

    # 4. Determine page count
    if doc_type == 'pdf':
        page_count = inspect_pdf_pages(file_obj)
        display_type = "PDF"
    elif doc_type == 'image':
        page_count = inspect_image_pages(file_obj)
        display_type = "Image (JPEG/PNG)"
    elif doc_type == 'docx':
        page_count = render_and_count_document_pages(file_obj, filename, 'docx', sha256_hash)
        display_type = "Microsoft Word (DOCX)"
    elif doc_type == 'doc':
        page_count = render_and_count_document_pages(file_obj, filename, 'doc', sha256_hash)
        display_type = "Legacy Word (DOC)"
    elif doc_type == 'pptx':
        page_count = render_and_count_document_pages(file_obj, filename, 'pptx', sha256_hash)
        display_type = "PowerPoint Presentation (PPTX)"
    elif doc_type == 'ppt':
        page_count = render_and_count_document_pages(file_obj, filename, 'ppt', sha256_hash)
        display_type = "Legacy PowerPoint (PPT)"
    elif doc_type == 'rtf':
        page_count = render_and_count_document_pages(file_obj, filename, 'rtf', sha256_hash)
        display_type = "Rich Text Format (RTF)"
    elif doc_type == 'txt':
        page_count = render_and_count_document_pages(file_obj, filename, 'txt', sha256_hash)
        display_type = "Plain Text (TXT)"
    else:
        raise DocumentInspectionError(f"Unsupported document type: {doc_type}")

    return {
        "filename": filename or "document",
        "file_size": file_size,
        "doc_type": display_type,
        "page_count": page_count,
        "sha256": sha256_hash,
        "status": "Ready to print"
    }
