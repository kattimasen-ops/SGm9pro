#!/usr/bin/env python3
"""Smokin' Guns ARM64 (RK3326 / Cortex-A35) build patcher."""

import os
import re
import sys
import glob
import shutil
import traceback
import subprocess
import urllib.request
import urllib.parse
import html.parser


class DirectoryParser(html.parser.HTMLParser):
    EXCLUDED_FILES = {"sg_pak0.pk3"}

    def __init__(self):
        super().__init__()
        self.files = []
        self.subdirs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr, value in attrs:
                if attr == 'href':
                    if '?' in value or value == '/' or value.startswith('http') or '..' in value:
                        continue
                    if value.endswith('/'):
                        self.subdirs.append(value)
                    elif value.lower().endswith('.pk3') and value not in self.EXCLUDED_FILES:
                        self.files.append(value)


def run(cmd, **kw):
    printable = cmd if isinstance(cmd, str) else " ".join(str(x) for x in cmd)
    print(f"[RUN] {printable}", flush=True)
    subprocess.run(cmd, check=True, **kw)


def build_sdl12_compat(prefix="/usr/local"):
    src = "/tmp/sdl12-compat-src"
    bld = "/tmp/sdl12-compat-build"
    for d in (src, bld):
        if os.path.exists(d):
            shutil.rmtree(d)
    print("[INFO] Cloning libsdl12-compat release-1.2.56 ...", flush=True)
    run(["git", "clone", "--depth=1", "--branch", "release-1.2.56",
         "https://github.com/libsdl-org/sdl12-compat.git", src])
    os.makedirs(bld, exist_ok=True)
    run(["cmake", src,
         "-DCMAKE_BUILD_TYPE=Release",
         f"-DCMAKE_INSTALL_PREFIX={prefix}",
         "-DSDL12DEVEL=ON",
         "-DSDL12TESTS=OFF"], cwd=bld)
    run(["make", "-j", str(os.cpu_count() or 2)], cwd=bld)
    run(["make", "install"], cwd=bld)
    subprocess.run(["ldconfig"], check=False)
    print("[PATCHED] libsdl12-compat built and installed.", flush=True)


def patch_makefile(path="Makefile"):
    with open(path, encoding="utf-8", errors="ignore") as f:
        c = f.read()
    c = re.sub(r'^ARCH\s*\?=\s*.*$',           'ARCH ?= aarch64',     c, flags=re.M)
    c = re.sub(r'^BUILD_GAME_SO\s*\?=\s*.*$',  'BUILD_GAME_SO ?= 1',  c, flags=re.M)
    c = re.sub(r'^BUILD_GAME_QVM\s*\?=\s*.*$', 'BUILD_GAME_QVM ?= 0', c, flags=re.M)
    c = re.sub(r'WIDTH\s*:=\s*\$\(shell\s+tput\s+cols[^\)]*\)',
               'WIDTH := $(shell tput cols 2>/dev/null || echo 80)', c)
    if '-DARCH_STRING=' not in c:
        c = re.sub(r'^(CFLAGS\s*\+=)',
                   r'\1 -DARCH_STRING=\\"$(ARCH)\\"',
                   c, count=1, flags=re.M)
    if 'Overrides added by patch_arm64.py' not in c:
        c = c.rstrip() + "\n\n" + (
            "# ---- Overrides added by patch_arm64.py ----\n"
            "SDL_CFLAGS = -I/usr/local/include/SDL -D_REENTRANT\n"
            "SDL_LIBS = -L/usr/local/lib -lSDL -lSDL2\n"
            "FREETYPE_CFLAGS = -I/usr/include/freetype2\n"
            "CFLAGS += $(SDL_CFLAGS)\n"
            "CLIENT_LIBS += $(SDL_LIBS)\n"
            "CFLAGS += $(FREETYPE_CFLAGS)\n"
            "BASE_CFLAGS += -Wno-error=implicit-function-declaration -Wno-implicit-function-declaration\n"
            "# ---- End of overrides ----\n"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("[PATCHED] Makefile.", flush=True)


def patch_q_platform(path="code/qcommon/q_platform.h"):
    with open(path, encoding="utf-8", errors="ignore") as f:
        c = f.read()
    if '__aarch64__' in c:
        print("[SKIP] q_platform.h already has AArch64 support.", flush=True)
        return
    blk = (
        "\n/* ---- AArch64 fallback ---- */\n"
        "#if defined(__aarch64__) && !defined(ARCH_STRING)\n"
        "#define ARCH_STRING \"aarch64\"\n"
        "#endif\n"
        "#if defined(__aarch64__) && !defined(CPUSTRING)\n"
        "#define CPUSTRING \"aarch64\"\n"
        "#endif\n"
        "#if defined(__aarch64__) && !defined(ID_LITTLE_ENDIAN)\n"
        "#define ID_LITTLE_ENDIAN 1\n"
        "#endif\n"
        "#if defined(__aarch64__) && !defined(id386)\n"
        "#define id386 0\n"
        "#endif\n"
        "/* ---- end AArch64 fallback ---- */\n"
    )
    m = re.search(r'(#define\s+\w+\s*\n)', c)
    if m:
        c = c[:m.end()] + blk + c[m.end():]
        with open(path, "w", encoding="utf-8") as f:
            f.write(c)
        print("[PATCHED] q_platform.h.", flush=True)


# Each entry: (return_type, name, params, call_args)
TRAP_DEFS = [
    ("void",      "trap_Print",                     "const char *string",                                     "UI_PRINT, string"),
    ("void",      "trap_Error",                     "const char *string",                                     "UI_ERROR, string"),
    ("int",       "trap_Milliseconds",              "void",                                                   "UI_MILLISECONDS"),
    ("void",      "trap_Cvar_Register",             "vmCvar_t *cvar, const char *var_name, const char *value, int flags", "UI_CVAR_REGISTER, cvar, var_name, value, flags"),
    ("void",      "trap_Cvar_Update",               "vmCvar_t *cvar",                                         "UI_CVAR_UPDATE, cvar"),
    ("void",      "trap_Cvar_Set",                  "const char *var_name, const char *value",                "UI_CVAR_SET, var_name, value"),
    ("float",     "trap_Cvar_VariableValue",        "const char *var_name",                                   "UI_CVAR_VARIABLEVALUE, var_name"),
    ("void",      "trap_Cvar_VariableStringBuffer", "const char *var_name, char *buffer, int bufsize",        "UI_CVAR_VARIABLESTRINGBUFFER, var_name, buffer, bufsize"),
    ("void",      "trap_Cvar_SetValue",             "const char *var_name, float value",                      "UI_CVAR_SETVALUE, var_name, PASSFLOAT(value)"),
    ("void",      "trap_Cvar_Reset",                "const char *name",                                       "UI_CVAR_RESET, name"),
    ("void",      "trap_Cvar_Create",               "const char *var_name, const char *var_value, int flags", "UI_CVAR_CREATE, var_name, var_value, flags"),
    ("void",      "trap_Cvar_InfoStringBuffer",     "int bit, char *buffer, int bufsize",                     "UI_CVAR_INFOSTRINGBUFFER, bit, buffer, bufsize"),
    ("int",       "trap_Argc",                      "void",                                                   "UI_ARGC"),
    ("void",      "trap_Argv",                      "int n, char *buffer, int bufferLength",                  "UI_ARGV, n, buffer, bufferLength"),
    ("void",      "trap_Cmd_ExecuteText",           "int exec_when, const char *text",                        "UI_CMD_EXECUTETEXT, exec_when, text"),
    ("void",      "trap_FS_FOpenFile",              "const char *qpath, fileHandle_t *f, fsMode_t mode",      "UI_FS_FOPENFILE, qpath, f, mode"),
    ("void",      "trap_FS_Read",                   "void *buffer, int len, fileHandle_t f",                  "UI_FS_READ, buffer, len, f"),
    ("void",      "trap_FS_Write",                  "const void *buffer, int len, fileHandle_t f",            "UI_FS_WRITE, buffer, len, f"),
    ("void",      "trap_FS_FCloseFile",             "fileHandle_t f",                                         "UI_FS_FCLOSEFILE, f"),
    ("int",       "trap_FS_GetFileList",            "const char *path, const char *extension, char *listbuf, int bufsize", "UI_FS_GETFILELIST, path, extension, listbuf, bufsize"),
    ("int",       "trap_FS_Seek",                   "fileHandle_t f, long offset, int origin",                "UI_FS_SEEK, f, offset, origin"),
    ("qhandle_t", "trap_R_RegisterModel",           "const char *name",                                       "UI_R_REGISTERMODEL, name"),
    ("qhandle_t", "trap_R_RegisterSkin",            "const char *name",                                       "UI_R_REGISTERSKIN, name"),
    ("qhandle_t", "trap_R_RegisterShaderNoMip",     "const char *name",                                       "UI_R_REGISTERSHADERNOMIP, name"),
    ("void",      "trap_R_ClearScene",              "void",                                                   "UI_R_CLEARSCENE"),
    ("void",      "trap_R_AddRefEntityToScene",     "const refEntity_t *re",                                  "UI_R_ADDREFENTITYTOSCENE, re"),
    ("void",      "trap_R_AddPolyToScene",          "qhandle_t hShader, int numVerts, const polyVert_t *verts", "UI_R_ADDPOLYTOSCENE, hShader, numVerts, verts"),
    ("void",      "trap_R_AddLightToScene",         "const vec3_t org, float intensity, float r, float g, float b", "UI_R_ADDLIGHTTOSCENE, org, PASSFLOAT(intensity), PASSFLOAT(r), PASSFLOAT(g), PASSFLOAT(b)"),
    ("void",      "trap_R_RenderScene",             "const refdef_t *fd",                                     "UI_R_RENDERSCENE, fd"),
    ("void",      "trap_R_SetColor",                "const float *rgba",                                      "UI_R_SETCOLOR, rgba"),
    ("void",      "trap_R_DrawStretchPic",          "float x, float y, float w, float h, float s1, float t1, float s2, float t2, qhandle_t hShader", "UI_R_DRAWSTRETCHPIC, PASSFLOAT(x), PASSFLOAT(y), PASSFLOAT(w), PASSFLOAT(h), PASSFLOAT(s1), PASSFLOAT(t1), PASSFLOAT(s2), PASSFLOAT(t2), hShader"),
    ("void",      "trap_UpdateScreen",              "void",                                                   "UI_UPDATESCREEN"),
    ("int",       "trap_CM_LerpTag",                "orientation_t *tag, clipHandle_t mod, int startFrame, int endFrame, float frac, const char *tagName", "UI_CM_LERPTAG, tag, mod, startFrame, endFrame, PASSFLOAT(frac), tagName"),
    ("void",      "trap_S_StartLocalSound",         "sfxHandle_t sfx, int channelNum",                        "UI_S_STARTLOCALSOUND, sfx, channelNum"),
    ("void",      "trap_S_RegisterSound",           "const char *sample, qboolean compressed",                "UI_S_REGISTERSOUND, sample, compressed"),
    ("void",      "trap_Key_KeynumToStringBuf",     "int keynum, char *buf, int buflen",                      "UI_KEY_KEYNUMTOSTRINGBUF, keynum, buf, buflen"),
    ("void",      "trap_Key_GetBindingBuf",         "int keynum, char *buf, int buflen",                      "UI_KEY_GETBINDINGBUF, keynum, buf, buflen"),
    ("void",      "trap_Key_SetBinding",            "int keynum, const char *binding",                        "UI_KEY_SETBINDING, keynum, binding"),
    ("qboolean",  "trap_Key_IsDown",                "int keynum",                                             "UI_KEY_ISDOWN, keynum"),
    ("qboolean",  "trap_Key_GetOverstrikeMode",     "void",                                                   "UI_KEY_GETOVERSTRIKEMODE"),
    ("void",      "trap_Key_SetOverstrikeMode",     "qboolean state",                                         "UI_KEY_SETOVERSTRIKEMODE, state"),
    ("void",      "trap_Key_ClearStates",           "void",                                                   "UI_KEY_CLEARSTATES"),
    ("int",       "trap_Key_GetCatcher",            "void",                                                   "UI_KEY_GETCATCHER"),
    ("void",      "trap_Key_SetCatcher",            "int catcher",                                            "UI_KEY_SETCATCHER, catcher"),
    ("void",      "trap_GetClipboardData",          "char *buf, int bufsize",                                 "UI_GETCLIPBOARDDATA, buf, bufsize"),
    ("void",      "trap_GetClientState",            "uiClientState_t *cs",                                    "UI_GETCLIENTSTATE, cs"),
    ("void",      "trap_GetGlconfig",               "glconfig_t *glconfig",                                   "UI_GETGLCONFIG, glconfig"),
    ("int",       "trap_GetConfigString",           "int index, char *buffer, int bufferSize",                "UI_GETCONFIGSTRING, index, buffer, bufferSize"),
    ("int",       "trap_LAN_GetServerCount",        "int source",                                             "UI_LAN_GETSERVERCOUNT, source"),
    ("void",      "trap_LAN_GetServerAddressString","int source, int n, char *buf, int buflen",               "UI_LAN_GETSERVERADDRESSSTRING, source, n, buf, buflen"),
    ("void",      "trap_LAN_GetServerInfo",         "int source, int n, char *buf, int buflen",               "UI_LAN_GETSERVERINFO, source, n, buf, buflen"),
    ("int",       "trap_LAN_GetServerPing",         "int source, int n",                                      "UI_LAN_GETSERVERPING, source, n"),
    ("int",       "trap_LAN_GetPingQueueCount",     "void",                                                   "UI_LAN_GETPINGQUEUECOUNT"),
    ("void",      "trap_LAN_ClearPing",             "int n",                                                  "UI_LAN_CLEARPING, n"),
    ("void",      "trap_LAN_GetPing",               "int n, char *buf, int buflen, int *pingtime",            "UI_LAN_GETPING, n, buf, buflen, pingtime"),
    ("void",      "trap_LAN_GetPingInfo",           "int n, char *buf, int buflen",                           "UI_LAN_GETPINGINFO, n, buf, buflen"),
    ("void",      "trap_LAN_MarkServerVisible",     "int source, int n, qboolean visible",                    "UI_LAN_MARKSERVERVISIBLE, source, n, visible"),
    ("int",       "trap_LAN_ServerIsVisible",       "int source, int n",                                      "UI_LAN_SERVERISVISIBLE, source, n"),
    ("qboolean",  "trap_LAN_UpdateVisiblePings",    "int source",                                             "UI_LAN_UPDATEVISIBLEPINGS, source"),
    ("int",       "trap_LAN_AddServer",             "int source, const char *name, const char *addr",         "UI_LAN_ADDSERVER, source, name, addr"),
    ("void",      "trap_LAN_RemoveServer",          "int source, const char *addr",                           "UI_LAN_REMOVESERVER, source, addr"),
    ("void",      "trap_LAN_ResetPings",            "int n",                                                  "UI_LAN_RESETPINGS, n"),
    ("int",       "trap_LAN_ServerStatus",          "const char *serverAddress, char *serverStatus, int maxLen", "UI_LAN_SERVERSTATUS, serverAddress, serverStatus, maxLen"),
    ("int",       "trap_LAN_CompareServers",        "int source, int sortKey, int sortDir, int s1, int s2",   "UI_LAN_COMPARESERVERS, source, sortKey, sortDir, s1, s2"),
    ("void",      "trap_LAN_SaveCachedServers",     "void",                                                   "UI_LAN_SAVECACHEDSERVERS"),
    ("void",      "trap_LAN_LoadCachedServers",     "void",                                                   "UI_LAN_LOADCACHEDSERVERS"),
]


def create_ui_syscalls(path="code/ui/ui_syscalls.c"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    parts = [
        "/* ui_syscalls.c - auto-generated by patch_arm64.py */",
        "#include <stdint.h>",
        '#include "ui_local.h"',
        "#ifdef Q3_VM",
        '#error "Do not use in VM build"',
        "#endif",
        "",
        "static intptr_t (QDECL *syscall)(intptr_t arg, ...) = "
        "(intptr_t (QDECL *)(intptr_t, ...)) - 1;",
        "",
        "void QDECL dllEntry(intptr_t (QDECL *syscallptr)(intptr_t arg, ...)) {",
        "    syscall = syscallptr;",
        "}",
        "",
        "int PASSFLOAT(float x) {",
        "    floatint_t fi;",
        "    fi.f = x;",
        "    return fi.i;",
        "}",
        "",
    ]
    for ret, name, args, call in TRAP_DEFS:
        parts.append(f"{ret} {name}( {args} ) {{")
        parts.append(f"    syscall( {call} );")
        parts.append("}")
        parts.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"[PATCHED] Wrote {path}", flush=True)


def inject_neon(path="code/qcommon/q_math.c"):
    with open(path, encoding="utf-8", errors="ignore") as f:
        c = f.read()
    if "arm_neon.h" in c:
        print("[SKIP] NEON already injected.", flush=True)
        return
    blk = (
        "#if defined(__aarch64__)\n"
        "#include <arm_neon.h>\n"
        "float Q_rsqrt(float number) {\n"
        "    float32x4_t v = vdupq_n_f32(number);\n"
        "    float32x4_t vr = vrsqrteq_f32(v);\n"
        "    vr = vmulq_f32(vr, vrsqrtsq_f32(vmulq_f32(v, vr), vr));\n"
        "    return vgetq_lane_f32(vr, 0);\n"
        "}\n"
        "#else\n"
    )
    nc, n = re.subn(r'(float\s+Q_rsqrt\s*\(\s*float\s+number\s*\)\s*\{)',
                    blk + r'\1', c, count=1)
    if n == 0:
        print("[WARN] Q_rsqrt not found - NEON skipped.", flush=True)
        return
    m = re.search(r'(float\s+Q_rsqrt\s*\(.*?return.*?\n\})', nc, flags=re.S)
    if m:
        nc = nc[:m.end()] + "\n#endif\n" + nc[m.end():]
    with open(path, "w", encoding="utf-8") as f:
        f.write(nc)
    print("[PATCHED] NEON Q_rsqrt.", flush=True)


def inject_simd():
    for f in glob.glob("code/**/bg_pmove.c", recursive=True):
        with open(f, encoding="utf-8", errors="ignore") as fh:
            c = fh.read()
        if "#pragma omp simd" in c:
            print("[SKIP] SIMD pragma already present.", flush=True)
            return
        m = re.search(r'(for\s*\(\s*i\s*=\s*0\s*;\s*i\s*<\s*pm->numtouch\s*;)', c)
        if m:
            c = c[:m.start()] + "#pragma omp simd aligned(pm->touchents: 16)\n\t" + c[m.start():]
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(c)
            print("[PATCHED] SIMD pragma.", flush=True)
            return


def install_newer_cmake():
    print("[INFO] Upgrading CMake via pip ...", flush=True)
    run(["python3", "-m", "pip", "install", "--upgrade", "pip"])
    run(["python3", "-m", "pip", "install", "cmake>=3.18"])
    r = subprocess.run(["cmake", "--version"], capture_output=True, text=True, check=True)
    print(f"[INFO] {r.stdout.splitlines()[0]}", flush=True)


def build_mimalloc(prefix="build/release-linux-aarch64"):
    src = "/tmp/mimalloc-src"
    bld = "/tmp/mimalloc-build"
    for d in (src, bld):
        if os.path.exists(d):
            shutil.rmtree(d)
    print("[INFO] Cloning mimalloc ...", flush=True)
    run(["git", "clone", "--depth=1",
         "https://github.com/microsoft/mimalloc.git", src])
    os.makedirs(bld, exist_ok=True)
    cflags = ("-O3 -mcpu=cortex-a35 -mtune=cortex-a35 -fomit-frame-pointer "
              "-fno-stack-protector -fno-asynchronous-unwind-tables "
              "-fmerge-all-constants -falign-functions=16 -falign-loops=16 "
              "-DNDEBUG -w -fcommon -fno-unroll-loops")
    run(["cmake", src,
         "-DCMAKE_BUILD_TYPE=Release",
         "-DMI_BUILD_SHARED=ON",
         "-DMI_BUILD_STATIC=OFF",
         "-DMI_BUILD_OBJECT=OFF",
         f"-DCMAKE_C_FLAGS={cflags}",
         f"-DCMAKE_INSTALL_PREFIX={os.path.abspath(prefix)}"], cwd=bld)
    run(["make", "-j", str(os.cpu_count() or 2)], cwd=bld)
    run(["make", "install"], cwd=bld)
    mod_dir = os.path.join(prefix, "smokinguns")
    os.makedirs(mod_dir, exist_ok=True)
    for lib in ("libmimalloc.so", "libmimalloc.so.3", "libmimalloc.so.3.5"):
        s = os.path.join(prefix, "lib", lib)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(mod_dir, lib))
    print("[PATCHED] mimalloc built and installed.", flush=True)


def crawl(base, target, sub="", depth=10):
    if depth <= 0:
        return
    url = urllib.parse.urljoin(base, sub)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = r.read().decode('utf-8', errors='ignore')
        p = DirectoryParser()
        p.feed(page)
        local = os.path.join(target, sub)
        os.makedirs(local, exist_ok=True)
        for fn in sorted(set(p.files)):
            dst = os.path.join(local, fn)
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                continue
            try:
                urllib.request.urlretrieve(urllib.parse.urljoin(url, fn), dst)
                print(f"  Downloaded {fn}", flush=True)
            except Exception as e:
                print(f"  FAILED {fn}: {e}", flush=True)
        for sd in sorted
