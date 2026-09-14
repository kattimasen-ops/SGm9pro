#!/usr/bin/env python3
import os, re, sys, glob, shutil, subprocess, urllib.request, urllib.parse, html.parser

def sh(cmd, **kw):
    print("+", cmd if isinstance(cmd, str) else " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)

def sdl12():
    for d in ("/tmp/sdl12-src", "/tmp/sdl12-bld"):
        if os.path.exists(d): shutil.rmtree(d)
    sh(["git","clone","--depth=1","--branch","release-1.2.56",
        "https://github.com/libsdl-org/sdl12-compat.git","/tmp/sdl12-src"])
    os.makedirs("/tmp/sdl12-bld", exist_ok=True)
    sh(["cmake","/tmp/sdl12-src","-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_INSTALL_PREFIX=/usr/local","-DSDL12DEVEL=ON","-DSDL12TESTS=OFF"],
       cwd="/tmp/sdl12-bld")
    sh(["make","-j"+str(os.cpu_count() or 2)], cwd="/tmp/sdl12-bld")
    sh(["make","install"], cwd="/tmp/sdl12-bld")
    subprocess.run(["ldconfig"], check=False)

def patch_makefile():
    c = open("Makefile").read()
    c = re.sub(r'^ARCH\s*\?=\s*.*$', 'ARCH ?= aarch64', c, flags=re.M)
    c = re.sub(r'^BUILD_GAME_SO\s*\?=\s*.*$', 'BUILD_GAME_SO ?= 1', c, flags=re.M)
    c = re.sub(r'^BUILD_GAME_QVM\s*\?=\s*.*$', 'BUILD_GAME_QVM ?= 0', c, flags=re.M)
    c = re.sub(r'WIDTH\s*:=\s*\$\(shell\s+tput\s+cols[^\)]*\)',
               'WIDTH := $(shell tput cols 2>/dev/null || echo 80)', c)
    if 'Overrides added by patch' not in c:
        c = c.rstrip() + (
            "\n\n# Overrides added by patch_arm64.py\n"
            "SDL_CFLAGS = -I/usr/local/include/SDL -D_REENTRANT\n"
            "SDL_LIBS = -L/usr/local/lib -lSDL -lSDL2\n"
            "FREETYPE_CFLAGS = -I/usr/include/freetype2\n"
            "CFLAGS += $(SDL_CFLAGS) $(FREETYPE_CFLAGS)\n"
            "CLIENT_LIBS += $(SDL_LIBS)\n"
            "BASE_CFLAGS += -Wno-error=implicit-function-declaration "
            "-Wno-implicit-function-declaration\n")
    open("Makefile","w").write(c)
    print("[OK] Makefile patched", flush=True)

def patch_qplat():
    p = "code/qcommon/q_platform.h"
    c = open(p).read()
    if '__aarch64__' in c:
        print("[SKIP] q_platform.h already patched", flush=True)
        return
    blk = ("\n/* AArch64 */\n"
           "#if defined(__aarch64__) && !defined(ARCH_STRING)\n"
           "#define ARCH_STRING \"aarch64\"\n#endif\n"
           "#if defined(__aarch64__) && !defined(CPUSTRING)\n"
           "#define CPUSTRING \"aarch64\"\n#endif\n"
           "#if defined(__aarch64__) && !defined(ID_LITTLE_ENDIAN)\n"
           "#define ID_LITTLE_ENDIAN 1\n#endif\n"
           "#if defined(__aarch64__) && !defined(id386)\n"
           "#define id386 0\n#endif\n")
    m = re.search(r'(#define\s+\w+\s*\n)', c)
    if m:
        open(p,"w").write(c[:m.end()] + blk + c[m.end():])
        print("[OK] q_platform.h patched", flush=True)

# One trap per line: ret|name|args|call
TRAP_DATA = """void|trap_Print|const char *string|UI_PRINT, string
void|trap_Error|const char *string|UI_ERROR, string
int|trap_Milliseconds|void|UI_MILLISECONDS
void|trap_Cvar_Register|vmCvar_t *cvar, const char *var_name, const char *value, int flags|UI_CVAR_REGISTER, cvar, var_name, value, flags
void|trap_Cvar_Update|vmCvar_t *cvar|UI_CVAR_UPDATE, cvar
void|trap_Cvar_Set|const char *var_name, const char *value|UI_CVAR_SET, var_name, value
float|trap_Cvar_VariableValue|const char *var_name|UI_CVAR_VARIABLEVALUE, var_name
void|trap_Cvar_VariableStringBuffer|const char *var_name, char *buffer, int bufsize|UI_CVAR_VARIABLESTRINGBUFFER, var_name, buffer, bufsize
void|trap_Cvar_SetValue|const char *var_name, float value|UI_CVAR_SETVALUE, var_name, PASSFLOAT(value)
void|trap_Cvar_Reset|const char *name|UI_CVAR_RESET, name
void|trap_Cvar_Create|const char *var_name, const char *var_value, int flags|UI_CVAR_CREATE, var_name, var_value, flags
void|trap_Cvar_InfoStringBuffer|int bit, char *buffer, int bufsize|UI_CVAR_INFOSTRINGBUFFER, bit, buffer, bufsize
int|trap_Argc|void|UI_ARGC
void|trap_Argv|int n, char *buffer, int bufferLength|UI_ARGV, n, buffer, bufferLength
void|trap_Cmd_ExecuteText|int exec_when, const char *text|UI_CMD_EXECUTETEXT, exec_when, text
void|trap_FS_FOpenFile|const char *qpath, fileHandle_t *f, fsMode_t mode|UI_FS_FOPENFILE, qpath, f, mode
void|trap_FS_Read|void *buffer, int len, fileHandle_t f|UI_FS_READ, buffer, len, f
void|trap_FS_Write|const void *buffer, int len, fileHandle_t f|UI_FS_WRITE, buffer, len, f
void|trap_FS_FCloseFile|fileHandle_t f|UI_FS_FCLOSEFILE, f
int|trap_FS_GetFileList|const char *path, const char *extension, char *listbuf, int bufsize|UI_FS_GETFILELIST, path, extension, listbuf, bufsize
int|trap_FS_Seek|fileHandle_t f, long offset, int origin|UI_FS_SEEK, f, offset, origin
qhandle_t|trap_R_RegisterModel|const char *name|UI_R_REGISTERMODEL, name
qhandle_t|trap_R_RegisterSkin|const char *name|UI_R_REGISTERSKIN, name
qhandle_t|trap_R_RegisterShaderNoMip|const char *name|UI_R_REGISTERSHADERNOMIP, name
void|trap_R_ClearScene|void|UI_R_CLEARSCENE
void|trap_R_AddRefEntityToScene|const refEntity_t *re|UI_R_ADDREFENTITYTOSCENE, re
void|trap_R_AddPolyToScene|qhandle_t hShader, int numVerts, const polyVert_t *verts|UI_R_ADDPOLYTOSCENE, hShader, numVerts, verts
void|trap_R_AddLightToScene|const vec3_t org, float intensity, float r, float g, float b|UI_R_ADDLIGHTTOSCENE, org, PASSFLOAT(intensity), PASSFLOAT(r), PASSFLOAT(g), PASSFLOAT(b)
void|trap_R_RenderScene|const refdef_t *fd|UI_R_RENDERSCENE, fd
void|trap_R_SetColor|const float *rgba|UI_R_SETCOLOR, rgba
void|trap_R_DrawStretchPic|float x, float y, float w, float h, float s1, float t1, float s2, float t2, qhandle_t hShader|UI_R_DRAWSTRETCHPIC, PASSFLOAT(x), PASSFLOAT(y), PASSFLOAT(w), PASSFLOAT(h), PASSFLOAT(s1), PASSFLOAT(t1), PASSFLOAT(s2), PASSFLOAT(t2), hShader
void|trap_UpdateScreen|void|UI_UPDATESCREEN
int|trap_CM_LerpTag|orientation_t *tag, clipHandle_t mod, int startFrame, int endFrame, float frac, const char *tagName|UI_CM_LERPTAG, tag, mod, startFrame, endFrame, PASSFLOAT(frac), tagName
void|trap_S_StartLocalSound|sfxHandle_t sfx, int channelNum|UI_S_STARTLOCALSOUND, sfx, channelNum
void|trap_S_RegisterSound|const char *sample, qboolean compressed|UI_S_REGISTERSOUND, sample, compressed
void|trap_Key_KeynumToStringBuf|int keynum, char *buf, int buflen|UI_KEY_KEYNUMTOSTRINGBUF, keynum, buf, buflen
void|trap_Key_GetBindingBuf|int keynum, char *buf, int buflen|UI_KEY_GETBINDINGBUF, keynum, buf, buflen
void|trap_Key_SetBinding|int keynum, const char *binding|UI_KEY_SETBINDING, keynum, binding
qboolean|trap_Key_IsDown|int keynum|UI_KEY_ISDOWN, keynum
qboolean|trap_Key_GetOverstrikeMode|void|UI_KEY_GETOVERSTRIKEMODE
void|trap_Key_SetOverstrikeMode|qboolean state|UI_KEY_SETOVERSTRIKEMODE, state
void|trap_Key_ClearStates|void|UI_KEY_CLEARSTATES
int|trap_Key_GetCatcher|void|UI_KEY_GETCATCHER
void|trap_Key_SetCatcher|int catcher|UI_KEY_SETCATCHER, catcher
void|trap_GetClipboardData|char *buf, int bufsize|UI_GETCLIPBOARDDATA, buf, bufsize
void|trap_GetClientState|uiClientState_t *cs|UI_GETCLIENTSTATE, cs
void|trap_GetGlconfig|glconfig_t *glconfig|UI_GETGLCONFIG, glconfig
int|trap_GetConfigString|int index, char *buffer, int bufferSize|UI_GETCONFIGSTRING, index, buffer, bufferSize
int|trap_LAN_GetServerCount|int source|UI_LAN_GETSERVERCOUNT, source
void|trap_LAN_GetServerAddressString|int source, int n, char *buf, int buflen|UI_LAN_GETSERVERADDRESSSTRING, source, n, buf, buflen
void|trap_LAN_GetServerInfo|int source, int n, char *buf, int buflen|UI_LAN_GETSERVERINFO, source, n, buf, buflen
int|trap_LAN_GetServerPing|int source, int n|UI_LAN_GETSERVERPING, source, n
int|trap_LAN_GetPingQueueCount|void|UI_LAN_GETPINGQUEUECOUNT
void|trap_LAN_ClearPing|int n|UI_LAN_CLEARPING, n
void|trap_LAN_GetPing|int n, char *buf, int buflen, int *pingtime|UI_LAN_GETPING, n, buf, buflen, pingtime
void|trap_LAN_GetPingInfo|int n, char *buf, int buflen|UI_LAN_GETPINGINFO, n, buf, buflen
void|trap_LAN_MarkServerVisible|int source, int n, qboolean visible|UI_LAN_MARKSERVERVISIBLE, source, n, visible
int|trap_LAN_ServerIsVisible|int source, int n|UI_LAN_SERVERISVISIBLE, source, n
qboolean|trap_LAN_UpdateVisiblePings|int source|UI_LAN_UPDATEVISIBLEPINGS, source
int|trap_LAN_AddServer|int source, const char *name, const char *addr|UI_LAN_ADDSERVER, source, name, addr
void|trap_LAN_RemoveServer|int source, const char *addr|UI_LAN_REMOVESERVER, source, addr
void|trap_LAN_ResetPings|int n|UI_LAN_RESETPINGS, n
int|trap_LAN_ServerStatus|const char *serverAddress, char *serverStatus, int maxLen|UI_LAN_SERVERSTATUS, serverAddress, serverStatus, maxLen
int|trap_LAN_CompareServers|int source, int sortKey, int sortDir, int s1, int s2|UI_LAN_COMPARESERVERS, source, sortKey, sortDir, s1, s2
void|trap_LAN_SaveCachedServers|void|UI_LAN_SAVECACHEDSERVERS
void|trap_LAN_LoadCachedServers|void|UI_LAN_LOADCACHEDSERVERS"""

def mk_ui_syscalls():
    os.makedirs("code/ui", exist_ok=True)
    out = ["/* auto-generated by patch_arm64.py */",
           "#include <stdint.h>",
           '#include "ui_local.h"',
           "static intptr_t (QDECL *syscall)(intptr_t arg, ...) = "
           "(intptr_t (QDECL *)(intptr_t, ...)) - 1;",
           "void QDECL dllEntry(intptr_t (QDECL *syscallptr)(intptr_t arg, ...)) {",
           "    syscall = syscallptr;", "}",
           "int PASSFLOAT(float x) { floatint_t fi; fi.f = x; return fi.i; }", ""]
    for line in TRAP_DATA.strip().split("\n"):
        ret, name, args, call = line.split("|")
        out += [f"{ret} {name}( {args} ) {{",
                f"    syscall( {call} );", "}", ""]
    open("code/ui/ui_syscalls.c","w").write("\n".join(out))
    print("[OK] ui_syscalls.c written", flush=True)

def neon():
    p = "code/qcommon/q_math.c"
    c = open(p).read()
    if 'arm_neon.h' in c:
        print("[SKIP] NEON already present", flush=True); return
    blk = ("#if defined(__aarch64__)\n#include <arm_neon.h>\n"
           "float Q_rsqrt(float number) {\n"
           "    float32x4_t v = vdupq_n_f32(number);\n"
           "    float32x4_t vr = vrsqrteq_f32(v);\n"
           "    vr = vmulq_f32(vr, vrsqrtsq_f32(vmulq_f32(v, vr), vr));\n"
           "    return vgetq_lane_f32(vr, 0);\n}\n#else\n")
    nc, n = re.subn(r'(float\s+Q_rsqrt\s*\(\s*float\s+number\s*\)\s*\{)',
                    blk + r'\1', c, count=1)
    if not n: print("[WARN] Q_rsqrt not found", flush=True); return
    m = re.search(r'(float\s+Q_rsqrt\s*\(.*?return.*?\n\})', nc, re.S)
    if m: nc = nc[:m.end()] + "\n#endif\n" + nc[m.end():]
    open(p,"w").write(nc)
    print("[OK] NEON injected", flush=True)

def simd():
    for f in glob.glob("code/**/bg_pmove.c", recursive=True):
        c = open(f).read()
        if '#pragma omp simd' in c:
            print("[SKIP] SIMD already present", flush=True); return
        m = re.search(r'(for\s*\(\s*i\s*=\s*0\s*;\s*i\s*<\s*pm->numtouch\s*;)', c)
        if m:
            open(f,"w").write(c[:m.start()] +
                "#pragma omp simd aligned(pm->touchents: 16)\n\t" +
                c[m.start():])
            print("[OK] SIMD pragma injected", flush=True); return

def cmake_up():
    sh(["python3","-m","pip","install","--upgrade","pip"])
    sh(["python3","-m","pip","install","cmake>=3.18"])

def mimalloc():
    for d in ("/tmp/mi-src","/tmp/mi-bld"):
        if os.path.exists(d): shutil.rmtree(d)
    sh(["git","clone","--depth=1",
        "https://github.com/microsoft/mimalloc.git","/tmp/mi-src"])
    os.makedirs("/tmp/mi-bld", exist_ok=True)
    cflags = ("-O3 -mcpu=cortex-a35 -mtune=cortex-a35 -fomit-frame-pointer "
              "-fno-stack-protector -fno-asynchronous-unwind-tables "
              "-fmerge-all-constants -falign-functions=16 -falign-loops=16 "
              "-DNDEBUG -w -fcommon -fno-unroll-loops")
    sh(["cmake","/tmp/mi-src","-DCMAKE_BUILD_TYPE=Release",
        "-DMI_BUILD_SHARED=ON","-DMI_BUILD_STATIC=OFF","-DMI_BUILD_OBJECT=OFF",
        f"-DCMAKE_C_FLAGS={cflags}",
        f"-DCMAKE_INSTALL_PREFIX={os.path.abspath('build/release-linux-aarch64')}"],
       cwd="/tmp/mi-bld")
    sh(["make","-j"+str(os.cpu_count() or 2)], cwd="/tmp/mi-bld")
    sh(["make","install"], cwd="/tmp/mi-bld")
    print("[OK] mimalloc built", flush=True)

def main():
    print("=" * 60, flush=True)
    print(" Smokin' Guns ARM64 Build Patcher", flush=True)
    print("=" * 60, flush=True)
    os.makedirs("build/release-linux-aarch64/smokinguns", exist_ok=True)
    subprocess.run(["git","config","--global","--add","safe.directory","/work"],
                   check=False, capture_output=True)
    sdl12()
    patch_makefile()
    patch_qplat()
    mk_ui_syscalls()
    neon()
    simd()
    cmake_up()
    mimalloc()
    cpu = os.cpu_count() or 2
    cc = os.environ.get("CC","gcc")
    opt = ("-O3 -mcpu=cortex-a35 -mtune=cortex-a35 -pipe -fomit-frame-pointer "
           "-ffast-math -ftree-vectorize -fno-math-errno -fno-trapping-math "
           "-fno-semantic-interposition -fno-stack-protector "
           "-fno-asynchronous-unwind-tables -fmerge-all-constants "
           "-falign-functions=16 -falign-loops=16 -DNDEBUG -w -fcommon "
           "-fopenmp-simd -flax-vector-conversions -mno-outline-atomics "
           "-fno-unroll-loops")
    cmd = (f'make -j{cpu} ARCH=aarch64 BUILD_GAME_SO=1 BUILD_GAME_QVM=0 '
           f'CC="{cc}" OPTIMIZE="{opt}" '
           f'LDFLAGS="-Wl,-O1 -Wl,--as-needed -Wl,--strip-all"')
    print(f"[INFO] {cmd}", flush=True)
    subprocess.run(cmd, shell=True, check=True)
    with open("build/release-linux-aarch64/smokinguns/autoexec.cfg","w") as f:
        f.write("// auto-generated\n")
        for line in ('seta s_musicvolume "0"','seta cg_boostfps "1"',
                     'seta cg_gunsmoke "0"','seta cg_glowflares "0"',
                     'seta r_picmip "5"','seta r_vertexLight "1"',
                     'seta r_dynamiclight "0"','seta r_fastsky "1"',
                     'seta com_maxfps "60"','seta com_busyWait "0"'):
            f.write(line + "\n")
    print("=" * 60, flush=True)
    print(" Build complete!", flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        sys.exit(1)
