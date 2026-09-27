"""Write the Windows version resource (Rinne.exe → Properties → Details) for PyInstaller.

    python packaging/windows/version_info.py build/version_info.txt
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rinne import AUTHOR, DISPLAY_NAME, __version__  # noqa: E402

nums = [int(x) for x in __version__.split(".")] + [0] * 4
v = tuple(nums[:4])
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{AUTHOR}'),
      StringStruct('FileDescription', '{DISPLAY_NAME} — weekly anime planner'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{DISPLAY_NAME}'),
      StringStruct('LegalCopyright', '© 2026 {AUTHOR} — MIT License'),
      StringStruct('OriginalFilename', '{DISPLAY_NAME}.exe'),
      StringStruct('ProductName', '{DISPLAY_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = Path(sys.argv[1] if len(sys.argv) > 1 else "version_info.txt")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(text, encoding="utf-8")
print(f"wrote {out} for {DISPLAY_NAME} {__version__}")
