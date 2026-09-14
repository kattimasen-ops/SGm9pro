#!/usr/bin/env python3
"""
Smokin' Guns ARM64 (RK3326 / Cortex-A35) build patcher.
Fixes ARCH_STRING, SDL12-compat (v1.2.56), FreeType, implicit function
declarations, injects NEON math, OpenMP SIMD, builds mimalloc,
mirrors .pk3 game assets, and writes a performance autoexec.cfg.
"""

import os
import re
import sys
import glob
import traceback
import subprocess
import urllib.request
import urllib.parse
import html.parser
import shutil

# ===========================================================================
# Directory listing parser (only .pk3 files)
# ===========================================================================
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
                    elif value.lower().endswith('.pk3'):
                        if value not in self.EXCLUDED_FILES:
                            self.files.append(value)

# ===========================================================================
# libsdl12-compat v1.2.56 (compatible with SDL 2.0.10)
# ===========================================================================
def build_libsdl12_compat(install_prefix="/usr/local"):
    src_dir = "/tmp/sdl12-compat-src"
    build_dir = "/tmp/sdl12-compat-build"

    if os.path.exists(src_dir):
        shutil.rmtree(src_dir)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    print("[INFO] Cloning libsdl12-compat v1.2.56 (compatible with SDL 2.0.10)...", flush=True)
    subprocess.run(
        ["git", "clone", "--depth=1", "--branch", "release-1.2.56",
         "https://github.com/libsdl-org/sdl12-compat.git", src_dir],
        check=True
    )
    os.makedirs(build_dir, exist_ok=True)

    print("[INFO] Configuring libsdl12-compat with CMake...", flush=True)
    subprocess.run(
        ["cmake", src_dir,
         "-DCMAKE_BUILD_TYPE=Release",
         "-DCMAKE_INSTALL_PREFIX=" + install_prefix,
         "-DSDL12DEVEL=ON",
         "-DSDL12TESTS=OFF"],
        cwd=build_dir, check=True
    )
    print("[INFO] Building libsdl12-compat...", flush=True)
    subprocess.run(["make", "-j", str(os.cpu_count() or 2)], cwd=build_dir, check=True)

    print("[INFO] Installing libsdl12-compat...", flush=True)
    subprocess.run(["make", "install"], cwd=build_dir, check=True)
    subprocess.run(["ldconfig"], check=False)

    for h in ["SDL_keysym.h", "SDL.h"]:
        path = os.path.join(install_prefix, "include", "SDL", h)
        if os.path.exists(path):
            print(f"[INFO] Header installed: {path}", flush=True)
        else:
            print(f"[WARN] Header not found: {path}", flush=True)
    print("[PATCHED] libsdl12-compat v1.2.56 built and installed.", flush=True)

# ===========================================================================
# Makefile patch (includes FreeType, SDL12-compat, and implicit-function fix)
# ===========================================================================
def patch_makefile(filepath="Makefile"):
    if not os.path.exists(filepath):
        print(f"Error: Makefile not found at {filepath}", flush=True)
        return False
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content = re.sub(r'^ARCH\s*\?=\s*.*$',
                     'ARCH ?= aarch64', content, flags=re.MULTILINE)
    content = re.sub(r'^BUILD_GAME_SO\s*\?=\s*.*$',
                     'BUILD_GAME_SO ?= 1', content, flags=re.MULTILINE)
    content = re.sub(r'^BUILD_GAME_QVM\s*\?=\s*.*$',
                     'BUILD_GAME_QVM ?= 0', content, flags=re.MULTILINE)

    content = re.sub(
        r'WIDTH\s*:=\s*\$\(shell\s+tput\s+cols[^\)]*\)',
        'WIDTH := $(shell tput cols 2>/dev/null || echo 80)',
        content
    )
    if '-DARCH_STRING=' not in content:
        content = re.sub(
            r'^(CFLAGS\s*\+=)',
            r'\1 -DARCH_STRING=\\"$(ARCH)\\"',
            content, count=1, flags=re.MULTILINE
        )

    overrides = (
        "\n"
        "# ---- Overrides added by patch_arm64.py ----\n"
        "SDL_CFLAGS = -I/usr/local/include/SDL -D_REENTRANT\n"
        "SDL_LIBS = -L/usr/local/lib -lSDL -lSDL2\n"
        "FREETYPE_CFLAGS = -I/usr/include/freetype2\n"
        "ifneq ($(SDL_CFLAGS),)\n"
        "  CFLAGS += $(SDL_CFLAGS)\n"
        "endif\n"
        "ifneq ($(SDL_LIBS),)\n"
        "  CLIENT_LIBS += $(SDL_LIBS)\n"
        "endif\n"
        "ifneq ($(FREETYPE_CFLAGS),)\n"
        "  CFLAGS += $(FREETYPE_CFLAGS)\n"
        "endif\n"
        "BASE_CFLAGS += -Wno-error=implicit-function-declaration -Wno-implicit-function-declaration\n"
        "# ---- End of overrides ----\n"
    )
    if 'Overrides added by patch_arm64.py' not in content:
        content = content.rstrip() + "\n" + overrides + "\n"

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[PATCHED] Makefile: ARCH, BUILD_GAME_SO, BUILD_GAME_QVM, "
          "WIDTH, ARCH_STRING, SDL12-compat, FreeType, implicit-function flags", flush=True)
    return True

# ===========================================================================
# q_platform.h patch
# ===========================================================================
def patch_q_platform(filepath="code/qcommon/q_platform.h"):
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found", flush=True)
        return False
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if '__aarch64__' in content:
        print("[SKIP] q_platform.h already has AArch64 support.", flush=True)
        return False
    aarch64_fallback = (
        "\n"
        "/* ---- AArch64 (ARM64) fallback support ---- */\n"
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
    match = re.search(r'(#define\s+\w+\s*\n)', content)
    if match:
        insert_pos = match.end()
        content = content[:insert_pos] + aarch64_fallback + content[insert_pos:]
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[PATCHED] AArch64 fallback block added to q_platform.h.", flush=True)
        return True
    print("[WARN] Could not find insertion point in q_platform.h", flush=True)
    return False

# ===========================================================================
# ui_syscalls.c creation (shared-library build) — always overwrites
# ===========================================================================
def create_ui_syscalls(filepath="code/ui/ui_syscalls.c"):
    # Force-clean anything previously at this path.
    if os.path.isdir(filepath):
        shutil.rmtree(filepath)
    elif os.path.exists(filepath):
        os.remove(filepath)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    content = r'''/*
===========================================================================
Copyright (C) 1999-2005 Id Software, Inc.
Copyright (C) 2000-2010 Smokin' Guns

This file is part of Smokin' Guns.

Smokin' Guns is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

Smokin' Guns is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Smokin' Guns; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
===========================================================================
*/

#include "ui_local.h"

// this file is only included when building a dll
// syscalls.asm is included instead when building a qvm
#ifdef Q3_VM
#error "Do not use in VM build"
#endif

static intptr_t (QDECL *syscall)( intptr_t arg, ... ) = (intptr_t (QDECL *)( intptr_t, ...)) - 1;

void QDECL dllEntry( intptr_t (QDECL *syscallptr)( intptr_t arg, ... ) ) {
    syscall = syscallptr;
}

int PASSFLOAT( float x ) {
    floatint_t fi;
    fi.f = x;
    return fi.i;
}

void trap_Print( const char *string ) {
    syscall( UI_PRINT, string );
}

void trap_Error( const char *string ) {
    syscall( UI_ERROR, string );
}

int trap_Milliseconds( void ) {
    return syscall( UI_MILLISECONDS );
}

void trap_Cvar_Register( vmCvar_t *cvar, const char *var_name, const char *value, int flags ) {
    syscall( UI_CVAR_REGISTER, cvar, var_name, value, flags );
}

void trap_Cvar_Update( vmCvar_t *cvar ) {
    syscall( UI_CVAR_UPDATE, cvar );
}

void trap_Cvar_Set( const char *var_name, const char *value ) {
    syscall( UI_CVAR_SET, var_name, value );
}

float trap_Cvar_VariableValue( const char *var_name ) {
    intptr_t temp;
    temp = syscall( UI_CVAR_VARIABLEVALUE, var_name );
    return (*(float*)&temp);
}

void trap_Cvar_VariableStringBuffer( const char *var_name, char *buffer, int bufsize ) {
    syscall( UI_CVAR_VARIABLESTRINGBUFFER, var_name, buffer, bufsize );
}

void trap_Cvar_SetValue( const char *var_name, float value ) {
    syscall( UI_CVAR_SETVALUE, var_name, PASSFLOAT( value ) );
}

void trap_Cvar_Reset( const char *name ) {
    syscall( UI_CVAR_RESET, name );
}

void trap_Cvar_Create( const char *var_name, const char *var_value, int flags ) {
    syscall( UI_CVAR_CREATE, var_name, var_value, flags );
}

void trap_Cvar_InfoStringBuffer( int bit, char *buffer, int bufsize ) {
    syscall( UI_CVAR_INFOSTRINGBUFFER, bit, buffer, bufsize );
}

int trap_Argc( void ) {
    return syscall( UI_ARGC );
}

void trap_Argv( int n, char *buffer, int bufferLength ) {
    syscall( UI_ARGV, n, buffer, bufferLength );
}

void trap_Cmd_ExecuteText( int exec_when, const char *text ) {
    syscall( UI_CMD_EXECUTETEXT, exec_when, text );
}

void trap_FS_FOpenFile( const char *qpath, fileHandle_t *f, fsMode_t mode ) {
    syscall( UI_FS_FOPENFILE, qpath, f, mode );
}

void trap_FS_Read( void *buffer, int len, fileHandle_t f ) {
    syscall( UI_FS_READ, buffer, len, f );
}

void trap_FS_Write( const void *buffer, int len, fileHandle_t f ) {
    syscall( UI_FS_WRITE, buffer, len, f );
}

void trap_FS_FCloseFile( fileHandle_t f ) {
    syscall( UI_FS_FCLOSEFILE, f );
}

int trap_FS_GetFileList( const char *path, const char *extension, char *listbuf, int bufsize ) {
    return syscall( UI_FS_GETFILELIST, path, extension, listbuf, bufsize );
}

int trap_FS_Seek( fileHandle_t f, long offset, int origin ) {
    return syscall( UI_FS_SEEK, f, offset, origin );
}

qhandle_t trap_R_RegisterModel( const char *name ) {
    return syscall( UI_R_REGISTERMODEL, name );
}

qhandle_t trap_R_RegisterSkin( const char *name ) {
    return syscall( UI_R_REGISTERSKIN, name );
}

qhandle_t trap_R_RegisterShaderNoMip( const char *name ) {
    return syscall( UI_R_REGISTERSHADERNOMIP, name );
}

void trap_R_ClearScene( void ) {
    syscall( UI_R_CLEARSCENE );
}

void trap_R_AddRefEntityToScene( const refEntity_t *re ) {
    syscall( UI_R_ADDREFENTITYTOSCENE, re );
}

void trap_R_AddPolyToScene( qhandle_t hShader, int numVerts, const polyVert_t *verts ) {
    syscall( UI_R_ADDPOLYTOSCENE, hShader, numVerts, verts );
}

void trap_R_AddLightToScene( const vec3_t org, float intensity, float r, float g, float b ) {
    syscall( UI_R_ADDLIGHTTOSCENE, org, PASSFLOAT(intensity), PASSFLOAT(r), PASSFLOAT(g), PASSFLOAT(b) );
}

void trap_R_RenderScene( const refdef_t *fd ) {
    syscall( UI_R_RENDERSCENE, fd );
}

void trap_R_SetColor( const float *rgba ) {
    syscall( UI_R_SETCOLOR, rgba );
}

void trap_R_DrawStretchPic( float x, float y, float w, float h, float s1, float t1, float s2, float t2, qhandle_t hShader ) {
    syscall( UI_R_DRAWSTRETCHPIC, PASSFLOAT(x), PASSFLOAT(y), PASSFLOAT(w), PASSFLOAT(h), PASSFLOAT(s1), PASSFLOAT(t1), PASSFLOAT(s2), PASSFLOAT(t2), hShader );
}

void trap_UpdateScreen( void ) {
    syscall( UI_UPDATESCREEN );
}

int trap_CM_LerpTag( orientation_t *tag, clipHandle_t mod, int startFrame, int endFrame, float frac, const char *tagName ) {
    return syscall( UI_CM_LERPTAG, tag, mod, startFrame, endFrame, PASSFLOAT(frac), tagName );
}

void trap_S_StartLocalSound( sfxHandle_t sfx, int channelNum ) {
    syscall( UI_S_STARTLOCALSOUND, sfx, channelNum );
}

void trap_S_RegisterSound( const char *sample, qboolean compressed ) {
    syscall( UI_S_REGISTERSOUND, sample, compressed );
}

void trap_Key_KeynumToStringBuf( int keynum, char *buf, int buflen ) {
    syscall( UI_KEY_KEYNUMTOSTRINGBUF, keynum, buf, buflen );
}

void trap_Key_GetBindingBuf( int keynum, char *buf, int buflen ) {
    syscall( UI_KEY_GETBINDINGBUF, keynum, buf, buflen );
}

void trap_Key_SetBinding( int keynum, const char *binding ) {
    syscall( UI_KEY_SETBINDING, keynum, binding );
}

qboolean trap_Key_IsDown( int keynum ) {
    return syscall( UI_KEY_ISDOWN, keynum );
}

qboolean trap_Key_GetOverstrikeMode( void ) {
    return syscall( UI_KEY_GETOVERSTRIKEMODE );
}

void trap_Key_SetOverstrikeMode( qboolean state ) {
    syscall( UI_KEY_SETOVERSTRIKEMODE, state );
}

void trap_Key_ClearStates( void ) {
    syscall( UI_KEY_CLEARSTATES );
}

int trap_Key_GetCatcher( void ) {
    return syscall( UI_KEY_GETCATCHER );
}

void trap_Key_SetCatcher( int catcher ) {
    syscall( UI_KEY_SETCATCHER, catcher );
}

void trap_GetClipboardData( char *buf, int bufsize ) {
    syscall( UI_GETCLIPBOARDDATA, buf, bufsize );
}

void trap_GetClientState( uiClientState_t *cs ) {
    syscall( UI_GETCLIENTSTATE, cs );
}

void trap_GetGlconfig( glconfig_t *glconfig ) {
    syscall( UI_GETGLCONFIG, glconfig );
}

int trap_GetConfigString( int index, char *buffer, int bufferSize ) {
    return syscall( UI_GETCONFIGSTRING, index, buffer, bufferSize );
}

int trap_LAN_GetServerCount( int source ) {
    return syscall( UI_LAN_GETSERVERCOUNT, source );
}

void trap_LAN_GetServerAddressString( int source, int n, char *buf, int buflen ) {
    syscall( UI_LAN_GETSERVERADDRESSSTRING, source, n, buf, buflen );
}

void trap_LAN_GetServerInfo( int source, int n, char *buf, int buflen ) {
    syscall( UI_LAN_GETSERVERINFO, source, n, buf, buflen );
}

int trap_LAN_GetServerPing( int source, int n ) {
    return syscall( UI_LAN_GETSERVERPING, source, n );
}

int trap_LAN_GetPingQueueCount( void ) {
    return syscall( UI_LAN_GETPINGQUEUECOUNT );
}

void trap_LAN_ClearPing( int n ) {
    syscall( UI_LAN_CLEARPING, n );
}

void trap_LAN_GetPing( int n, char *buf, int buflen, int *pingtime ) {
    syscall( UI_LAN_GETPING, n, buf, buflen, pingtime );
}

void trap_LAN_GetPingInfo( int n, char *buf, int buflen ) {
    syscall( UI_LAN_GETPINGINFO, n, buf, buflen );
}

void trap_LAN_MarkServerVisible( int source, int n, qboolean visible ) {
    syscall( UI_LAN_MARKSERVERVISIBLE, source, n, visible );
}

int trap_LAN_ServerIsVisible( int source, int n ) {
    return syscall( UI_LAN_SERVERISVISIBLE, source, n );
}

qboolean trap_LAN_UpdateVisiblePings( int source ) {
    return syscall( UI_LAN_UPDATEVISIBLEPINGS, source );
}

int trap_LAN_AddServer( int source, const char *name, const char *addr ) {
    return syscall( UI_LAN_ADDSERVER, source, name, addr );
}

void trap_LAN_RemoveServer( int source, const char *addr ) {
    syscall( UI_LAN_REMOVESERVER, source, addr );
}

void trap_LAN_ResetPings( int n ) {
    syscall( UI_LAN_RESETPINGS, n );
}

int trap_LAN_ServerStatus( const char *serverAddress, char *serverStatus, int maxLen ) {
    return syscall( UI_LAN_SERVERSTATUS, serverAddress, serverStatus, maxLen );
}

int trap_LAN_CompareServers( int source, int sortKey, int sortDir, int s1, int s2 ) {
    return syscall( UI_LAN_COMPARESERVERS, source, sortKey, sortDir, s1, s2 );
}

void trap_LAN_SaveCachedServers( void ) {
    syscall( UI_LAN_SAVECACHEDSERVERS );
}

void trap_LAN_LoadCachedServers( void ) {
    syscall( UI_LAN_LOADCACHEDSERVERS );
}
'''

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Wrote full {filepath} ({len(content)} bytes) for shared-library build.", flush=True)

# ===========================================================================
# NEON math injection
# ===========================================================================
def inject_neon_math(filepath="code/qcommon/q_math.c"):
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found", flush=True)
        return
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if "arm_neon.h" in content:
        print("[SKIP] NEON math already injected.", flush=True)
        return
    neon_code = (
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
    new_content, n = re.subn(
        r'(float\s+Q_rsqrt\s*\(\s*float\s+number\s*\)\s*\{)',
        neon_code + r'\1', content, count=1
    )
    if n == 0:
        print("[WARN] Q_rsqrt signature not found - NEON injection skipped.", flush=True)
        return
    pattern = r'(float\s+Q_rsqrt\s*\(.*?return.*?\n\})'
    match = re.search(pattern, new_content, flags=re.DOTALL)
    if not match:
        print("[WARN] Could not find end of Q_rsqrt - #endif missing.", flush=True)
        return
    end_pos = match.end()
    new_content = new_content[:end_pos] + "\n#endif\n" + new_content[end_pos:]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("[PATCHED] NEON-accelerated Q_rsqrt injected into q_math.c.", flush=True)

# ===========================================================================
# SIMD loop injection
# ===========================================================================
def inject_simd_by_pattern(filepath, pattern, alignment_var, description):
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found", flush=True)
        return
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if "#pragma omp simd" in content:
        print(f"[SKIP] OpenMP SIMD already present in {filepath}", flush=True)
        return
    match = re.search(pattern, content)
    if not match:
        print(f"[INFO] Pattern not found in {filepath} ({description}) - skipping.", flush=True)
        return
    insert_pos = match.start()
    pragma = f"#pragma omp simd aligned({alignment_var}: 16)\n\t"
    content = content[:insert_pos] + pragma + content[insert_pos:]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[PATCHED] SIMD pragma injected into {filepath} ({description}).", flush=True)

def find_and_patch_simd_loops():
    bg_pmove_candidates = glob.glob("code/**/bg_pmove.c", recursive=True)
    if bg_pmove_candidates:
        inject_simd_by_pattern(
