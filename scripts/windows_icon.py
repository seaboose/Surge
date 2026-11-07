"""Embed an authored ICO into a newly built Windows application executable.

Uses only the Windows resource API. Call only on the builder's private payload;
never on an installed application or an existing released executable.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import struct
import sys


def read_icon(path: Path):
    data = path.read_bytes()
    if len(data) < 6:
        raise ValueError("Truncated icon header")
    reserved, kind, count = struct.unpack_from("<HHH", data)
    if reserved or kind != 1 or not 1 <= count <= 32 or len(data) < 6 + count * 16:
        raise ValueError("Invalid icon directory")
    entries = []
    for index in range(count):
        width, height, colors, zero, planes, depth, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + index * 16)
        if zero or not size or offset < 6 + count * 16 or offset + size > len(data):
            raise ValueError("Invalid icon image bounds")
        entries.append(((width, height, colors, zero, planes, depth, size), data[offset:offset + size]))
    return entries


def embed_icon(executable: Path, icon: Path):
    if sys.platform != "win32":
        raise OSError("Executable icon embedding requires Windows")
    entries = read_icon(icon)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    kernel.LoadLibraryExW.restype = wintypes.HMODULE
    kernel.FreeLibrary.argtypes = [wintypes.HMODULE]
    kernel.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    kernel.UpdateResourceW.restype = wintypes.BOOL
    kernel.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    kernel.EndUpdateResourceW.restype = wintypes.BOOL
    names = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t)
    languages = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD, ctypes.c_ssize_t)
    kernel.EnumResourceNamesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, names, ctypes.c_ssize_t]
    kernel.EnumResourceLanguagesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, languages, ctypes.c_ssize_t]
    groups = []

    @names
    def group_name(module, resource_type, name, parameter):
        copied_name = name if name <= 65535 else ctypes.wstring_at(name)

        @languages
        def language(module, resource_type, name, lang, parameter):
            groups.append((copied_name, lang))
            return True

        kernel.EnumResourceLanguagesW(module, resource_type, name, language, 0)
        return True

    module = kernel.LoadLibraryExW(str(executable.resolve()), None, 2)
    if not module:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        kernel.EnumResourceNamesW(module, 14, group_name, 0)
    finally:
        kernel.FreeLibrary(module)
    if not groups:
        groups = [(1, 0)]
    group_data = struct.pack("<HHH", 0, 1, len(entries)) + b"".join(
        struct.pack("<BBBBHHIH", *fields, 60000 + index)
        for index, (fields, _) in enumerate(entries)
    )
    handle = kernel.BeginUpdateResourceW(str(executable.resolve()), False)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    def update(kind, name, lang, payload):
        identifier = ctypes.c_void_p(name) if isinstance(name, int) else ctypes.cast(ctypes.c_wchar_p(name), ctypes.c_void_p)
        buffer = ctypes.create_string_buffer(payload)
        if not kernel.UpdateResourceW(handle, kind, identifier, lang, buffer, len(payload)):
            raise ctypes.WinError(ctypes.get_last_error())

    try:
        for lang in {lang for _, lang in groups}:
            for index, (_, payload) in enumerate(entries):
                update(3, 60000 + index, lang, payload)
        for name, lang in groups:
            update(14, name, lang, group_data)
    except BaseException:
        kernel.EndUpdateResourceW(handle, True)
        raise
    if not kernel.EndUpdateResourceW(handle, False):
        raise ctypes.WinError(ctypes.get_last_error())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: windows_icon.py NEW_EXECUTABLE ICON_FILE")
    embed_icon(Path(sys.argv[1]), Path(sys.argv[2]))
