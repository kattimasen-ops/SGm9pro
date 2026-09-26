#!/usr/bin/env python3
"""
Smokin' Guns ARM64 patch (RK3326 / Cortex-A35).
v13.5 - Bugfixes + Logging.
v13.6 - Client Native VM (.so) Support.
v13.7 - Server Native VM (.so) Support.
v13.8 - Name-Rotator: nur bei Respawn.
v13.9 - VM pure-gate entfernt.
v14.0 - VM_Create erzwungen native.
v14.1 - Aim-Assist: Target-Scan nach Input (Respawn-Fix).
v14.2 - Crosshair rot, Hitmarker X-Form klein.
v14.3 - Damage-Indicator Ring-Dots, Enemy-Outline.
v14.4 - vm.c Pfad-Fix + Chat-Prefill v2.
v14.5 - Preset-Buttons: setcvar statt exec (UI-VM hat kein exec).
"""

import os
import re
import sys


AIM_CVAR_SUFFIXES = [
    "AimAssist", "AimAssistFire", "AimAssistAngle",
    "AimAssistStrength", "AimAssistFriction", "AimAssistPitch",
    "AimAssistLead", "AimAssistSticky", "AimAssistMaxDist",
    "AimAssistLOS", "AimAssistUnlaggedSync", "AimAssistInterpolate",
    "AimAssistSnapAngle", "AimAssistZoom", "AimAssistZoomNear",
    "AimAssistZoomFar", "AimAssistZoomFov", "AimAssistZoomSpeed",
    "AimAssistHardLock", "AutoSwitch", "HitMarker", "DamageIndicator",
    "AimPreset",
]


def diagnostic_dump():
    print("========== MAKEFILE DIAGNOSTIC DUMP ==========")
    for fname in ["Makefile", "Makefile.local", "Makefile.smokinguns"]:
        if not os.path.exists(fname):
            print(f"\n--- {fname} (NOT FOUND) ---")
            continue
        print(f"\n--- {fname} ---")
        with open(fname, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i < 150 or "ui" in line.lower() or "DIR" in line or "OBJ" in line:
                    print(f"{i+1:04d}: {line.rstrip()}")
    print("==============================================\n")


def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[WARN] {makefile} not found - skipping")
        return False
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "$(B)/$(BASENAME)/ui/" in content:
        content = content.replace("$(B)/$(BASENAME)/ui/", "$(B)/$(BASEGAME)/ui/")
        print("[PATCHED] Makefile: BASENAME -> BASEGAME in UI objects")
    sdl_include_line = "override CFLAGS += -I/usr/include/SDL\n"
    if "override CFLAGS += -I/usr/include/SDL" not in content:
        content = sdl_include_line + content
        print("[PATCHED] Makefile: added -I/usr/include/SDL to global CFLAGS")
    content = re.sub(r"\brm\s+(?!-)", "rm -f ", content)
    content = content.replace("python ", "python3 ")
    content = content.replace("python2 ", "python3 ")
    for pat in [r"-Werror[a-zA-Z0-9=-]*", r"-Wmaybe-uninitialized",
                r"-Wuninitialized", r"-Wstrict-overflow"]:
        content = re.sub(pat, "", content)
    for flag in ["-m32", "-m64", "-march=native", "march=native",
                 "-msse", "-msse2", "-msse3", "-mfpmath=sse"]:
        content = content.replace(flag, "")
    print("[PATCHED] Makefile: toxic x86 architecture flags removed")
    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_q_platform():
    patched = 0
    if not os.path.isdir("code"):
        return 0
    for root, _dirs, files in os.walk("code"):
        for name in files:
            if name != "q_platform.h":
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if re.search(r'ARCH_STRING\s+"aarch64"', content):
                continue
            pattern = re.compile(
                r'(#elif defined __arm__\s*\n#define ARCH_STRING "arm"\s*\n)')
            new_content, n = pattern.subn(
                r'\1#elif defined __aarch64__\n#define ARCH_STRING "aarch64"\n',
                content)
            if n > 0:
                content = new_content
            else:
                content = (
                    "/* [PATCHED] ARM64 ARCH_STRING override */\n"
                    "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
                    "#ifdef ARCH_STRING\n#undef ARCH_STRING\n#endif\n"
                    "#define ARCH_STRING \"aarch64\"\n"
                    "#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n"
                    "#endif\n\n"
                ) + content
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            patched += 1
            print(f"[PATCHED] {path}")
    return patched


def patch_sdl12_compat_hints():
    path = os.path.join("src", "SDL12_compat.c")
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "#ifndef SDL_HINT_VIDEODRIVER" in content:
        return True
    patch = (
        "/* [PATCHED] SDL_HINT fallbacks */\n"
        "#ifndef SDL_HINT_VIDEODRIVER\n"
        "#define SDL_HINT_VIDEODRIVER \"SDL_VIDEODRIVER\"\n"
        "#endif\n"
        "#ifndef SDL_HINT_AUDIODRIVER\n"
        "#define SDL_HINT_AUDIODRIVER \"SDL_AUDIODRIVER\"\n"
        "#endif\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(patch + content)
    print("[PATCHED] sdl12-compat: SDL_HINT_* fallbacks inserted")
    return True


def patch_client_cvar():
    path = os.path.join("code", "client", "cl_main.c")
    if not os.path.exists(path):
        print("[WARN] cl_main.c not found")
        return False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if 'cg_handheldNameRotate' in content:
        print("[SKIP] Client cvars already registered")
        return True
    anchor = 'j_up_axis =      Cvar_Get ("j_up_axis",      "2", CVAR_ARCHIVE);'
    if anchor not in content:
        print("[WARN] cl_main.c anchor not found")
        return False

    lines = [
        "\t/* [PATCHED v13.5] HHA cvars */",
        "\tCvar_Get (\"cg_handheldAimAssist\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistFire\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistAngle\", \"22\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistStrength\", \"0.55\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistFriction\", \"0.92\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistPitch\", \"0.80\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistLead\", \"0\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistSticky\", \"15\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistMaxDist\", \"3000\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistLOS\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistUnlaggedSync\", \"0\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistInterpolate\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistSnapAngle\", \"5\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoom\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomNear\", \"100\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomFar\", \"800\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomFov\", \"45\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomSpeed\", \"12\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistHardLock\", \"0\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAutoSwitch\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldHitMarker\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldDamageIndicator\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimPreset\", \"0\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistTargetDist\", \"0\", 0);",
        "\tCvar_Get (\"cg_handheldNameRotate\", \"0\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldNameInterval\", \"800\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldNameScheme\", \"0\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldChatPrefix\", \"\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldLog\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldEnemyOutline\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldEnemyOutlineRange\", \"2000\", CVAR_ARCHIVE);",
    ]
    content = content.replace(anchor, anchor + "\n" + "\n".join(lines), 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] cl_main.c: 32 cvars registered")
    return True


def patch_ui_cvar():
    ui_local_path = None
    for root, _dirs, files in os.walk("code"):
        if "ui_local.h" in files:
            ui_local_path = os.path.join(root, "ui_local.h")
            break
    if ui_local_path:
        with open(ui_local_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "ui_handheldAutoSwitch" not in content:
            anchor = "extern vmCvar_t\tui_brassTime;"
            if anchor in content:
                decls = "".join(
                    f"extern vmCvar_t\tui_handheld{sfx};\n"
                    for sfx in AIM_CVAR_SUFFIXES
                )
                content = content.replace(anchor, decls + anchor, 1)
                with open(ui_local_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"[PATCHED] ui_local.h: {len(AIM_CVAR_SUFFIXES)} extern decls")

    ui_main_path = None
    for root, _dirs, files in os.walk("code"):
        if "ui_main.c" in files:
            ui_main_path = os.path.join(root, "ui_main.c")
            break
    if not ui_main_path:
        print("[WARN] ui_main.c not found")
        return False
    with open(ui_main_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "ui_handheldAutoSwitch;" not in content:
        anchor = "vmCvar_t\tui_brassTime;"
        if anchor in content:
            decls = "".join(
                f"vmCvar_t\tui_handheld{sfx};\n"
                for sfx in AIM_CVAR_SUFFIXES
            )
            content = content.replace(anchor, decls + anchor, 1)
            print(f"[PATCHED] ui_main.c: {len(AIM_CVAR_SUFFIXES)} vmCvar_t decls")

    if '"cg_handheldAutoSwitch"' not in content:
        anchor = '\t{ &ui_brassTime, "cg_brassTime", "2500", CVAR_ARCHIVE },'
        if anchor in content:
            entries = (
                '\n\t{ &ui_handheldAimAssist, "cg_handheldAimAssist", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistFire, "cg_handheldAimAssistFire", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistAngle, "cg_handheldAimAssistAngle", "22", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistStrength, "cg_handheldAimAssistStrength", "0.55", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistFriction, "cg_handheldAimAssistFriction", "0.92", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistPitch, "cg_handheldAimAssistPitch", "0.80", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistLead, "cg_handheldAimAssistLead", "0", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistSticky, "cg_handheldAimAssistSticky", "15", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistMaxDist, "cg_handheldAimAssistMaxDist", "3000", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistLOS, "cg_handheldAimAssistLOS", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistUnlaggedSync, "cg_handheldAimAssistUnlaggedSync", "0", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistInterpolate, "cg_handheldAimAssistInterpolate", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistSnapAngle, "cg_handheldAimAssistSnapAngle", "5", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoom, "cg_handheldAimAssistZoom", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomNear, "cg_handheldAimAssistZoomNear", "100", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomFar, "cg_handheldAimAssistZoomFar", "800", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomFov, "cg_handheldAimAssistZoomFov", "45", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomSpeed, "cg_handheldAimAssistZoomSpeed", "12", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistHardLock, "cg_handheldAimAssistHardLock", "0", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAutoSwitch, "cg_handheldAutoSwitch", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldHitMarker, "cg_handheldHitMarker", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldDamageIndicator, "cg_handheldDamageIndicator", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimPreset, "cg_handheldAimPreset", "0", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldEnemyOutline, "cg_handheldEnemyOutline", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldEnemyOutlineRange, "cg_handheldEnemyOutlineRange", "2000", CVAR_ARCHIVE },'
            )
            content = content.replace(anchor, anchor + entries, 1)
            print("[PATCHED] ui_main.c: 25 cvarTable entries")

    with open(ui_main_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_aim_assist():
    """v14.1: Target-Scan laeuft NACH Maus/Joystick-Input."""
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cl_input.c" in files:
            target_file = os.path.join(root, "cl_input.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cl_input.c not found")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "CL_HandheldInputCurve" in content:
        print("[SKIP] Aim assist already present")
        return True

    helper_code = r"""
/* ============================================================
 * [PATCHED v14.1] Handheld Aim Assist (Client-Seite)
 * ============================================================ */
#include <math.h>

#ifndef ET_PLAYER
#define ET_PLAYER 1
#endif
#ifndef EF_DEAD
#define EF_DEAD 0x00000001
#endif

#define HHA_PI                3.14159265358979323846f
#define HHA_CURVE_EXP         1.02f
#define HHA_CURVE_REF        32.0f
#define HHA_MIN_DIST           48.0f
#define HHA_CHEST_HEIGHT     32.0f
#define HHA_FRICTION_MAX_MAG 40.0f
#define HHA_LOS_CACHE_SIZE   32
#define HHA_LOS_CACHE_MS    150
#define HHA_LOS_BUDGET        1
#define HHA_MAX_CANDIDATES   32
#define HHA_PULL_CAP_NORMAL 0.60f
#define HHA_PULL_CAP_SNAP   0.85f
#define HHA_ANGLE_CAP_LO      5.0f
#define HHA_ANGLE_CAP_HI     45.0f
#define HHA_ANGLE_CAP_AIM    89.0f
#define HHA_PITCH_LIMIT      89.0f

typedef struct {
    qboolean enabled;
    qboolean fireEnabled;
    qboolean losEnabled;
    qboolean unlaggedSync;
    qboolean interpolate;
    qboolean hardLock;
    float    angle;
    float    falloff;
    float    strengthYaw;
    float    strengthPitch;
    float    fireYaw;
    float    firePitch;
    float    friction;
    float    leadTime;
    int      stickyFrames;
    float    maxDist;
    float    snapAngle;
} hha_config_t;

typedef struct {
    int      entNum;
    int      checkTime;
    qboolean los;
    qboolean valid;
} hha_los_cache_entry_t;

typedef struct {
    int    entNum;
    float  angle;
    float  distSq;
    vec3_t dir;
    vec3_t feetPos;
} hha_candidate_t;

static hha_los_cache_entry_t hha_los_cache[HHA_LOS_CACHE_SIZE];
static int      hha_lastTargetNum = -1;
static int      hha_lastTargetAge = 0;
static int      hha_cachedTarget  = -1;
static float    hha_cachedAngle   = 999.0f;
static vec3_t   hha_cachedDir     = { 0, 0, 0 };
static qboolean hha_cachedValid   = qfalse;
static int      hha_losChecksThisFrame = 0;
static int      hha_lastSpawnCount = -1;
static int      hha_lastHealth = -999;
static int      hha_lastPmType = -1;
static qboolean hha_firstCall = qtrue;

static hha_config_t hha_cachedConfig;
static qboolean     hha_configValid = qfalse;
static float        hha_lastTargetDist = -1.0f;

static int hha_lastPreset = -2;
static int hha_lastAimHash = 0;
static int hha_lastPitchClampLog = 0;

static void HHA_Log(const char *fmt, ...) {
    va_list ap;
    char buf[512];
    fileHandle_t f;

    if (!Cvar_VariableIntegerValue("cg_handheldLog")) return;

    va_start(ap, fmt);
    Q_vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    f = FS_FOpenFileAppend("smokinguns_hha.log");
    if (!f) return;
    FS_Write("[HHA] ", 6, f);
    FS_Write(buf, strlen(buf), f);
    FS_Write("\n", 1, f);
    FS_FCloseFile(f);
}

static void HHA_ReadConfig( hha_config_t *cfg ) {
    int   hardLock = Cvar_VariableIntegerValue("cg_handheldAimAssistHardLock");
    float angle    = Cvar_VariableValue("cg_handheldAimAssistAngle");
    float strength = Cvar_VariableValue("cg_handheldAimAssistStrength");
    float friction = Cvar_VariableValue("cg_handheldAimAssistFriction");
    float pitchMul = Cvar_VariableValue("cg_handheldAimAssistPitch");
    float leadMs   = Cvar_VariableValue("cg_handheldAimAssistLead");
    float maxDist  = Cvar_VariableValue("cg_handheldAimAssistMaxDist");
    float snapAng  = Cvar_VariableValue("cg_handheldAimAssistSnapAngle");
    int   sticky   = Cvar_VariableIntegerValue("cg_handheldAimAssistSticky");
    float angleCapHi = hardLock ? HHA_ANGLE_CAP_AIM : HHA_ANGLE_CAP_HI;

    if ( angle    < HHA_ANGLE_CAP_LO ) angle    = HHA_ANGLE_CAP_LO;
    if ( angle    > angleCapHi )       angle    = angleCapHi;
    if ( strength <  0.05f )  strength =  0.05f;
    if ( strength >  1.20f )  strength =  1.20f;
    if ( friction <  0.50f )  friction =  0.50f;
    if ( friction >  1.00f )  friction =  1.00f;
    if ( pitchMul <  0.30f )  pitchMul =  0.30f;
    if ( pitchMul >  1.50f )  pitchMul =  1.50f;
    if ( leadMs   <  0.0f )   leadMs   =  0.0f;
    if ( leadMs   > 200.0f )  leadMs   = 200.0f;
    if ( maxDist  < 500.0f )  maxDist  = 500.0f;
    if ( maxDist  > 8000.0f ) maxDist  = 8000.0f;
    if ( snapAng  <  0.0f )   snapAng  =  0.0f;
    if ( snapAng  > 15.0f )   snapAng  = 15.0f;
    if ( sticky   < 0 )       sticky   = 0;
    if ( sticky   > 30 )      sticky   = 30;

    cfg->enabled       = ( Cvar_VariableIntegerValue("cg_handheldAimAssist") != 0 );
    cfg->fireEnabled   = ( Cvar_VariableIntegerValue("cg_handheldAimAssistFire") != 0 );
    cfg->losEnabled    = ( Cvar_VariableIntegerValue("cg_handheldAimAssistLOS") != 0 );
    cfg->unlaggedSync  = ( Cvar_VariableIntegerValue("cg_handheldAimAssistUnlaggedSync") != 0 );
    cfg->interpolate   = ( Cvar_VariableIntegerValue("cg_handheldAimAssistInterpolate") != 0 );
    cfg->hardLock      = ( hardLock != 0 );
    cfg->angle         = angle;
    cfg->falloff       = angle * 0.85f;
    cfg->strengthYaw   = strength;
    cfg->strengthPitch = strength * pitchMul;
    cfg->fireYaw       = strength * 1.875f;
    cfg->firePitch     = strength * pitchMul * 1.875f;
    cfg->friction      = friction;
    cfg->leadTime      = leadMs * 0.001f;
    cfg->stickyFrames  = sticky;
    cfg->maxDist       = maxDist;
    cfg->snapAngle     = snapAng;
}

static void HHA_RefreshConfig( void ) {
    HHA_ReadConfig( &hha_cachedConfig );
    hha_configValid = qtrue;
}

static void HHA_SetTargetDist( float d ) {
    if ( fabsf( d - hha_lastTargetDist ) > 0.5f ) {
        Cvar_Set( "cg_handheldAimAssistTargetDist", va( "%.1f", d ) );
        hha_lastTargetDist = d;
    }
}

static qboolean HHA_HasLineOfSight( int entNum, const vec3_t fromFeet, const vec3_t toFeet ) {
    trace_t tr;
    vec3_t  eye, chest;
    int     i, freeSlot = -1;

    eye[0] = fromFeet[0]; eye[1] = fromFeet[1];
    eye[2] = fromFeet[2] + cl.snap.ps.viewheight;
    chest[0] = toFeet[0]; chest[1] = toFeet[1];
    chest[2] = toFeet[2] + HHA_CHEST_HEIGHT;

    for ( i = 0; i < HHA_LOS_CACHE_SIZE; i++ ) {
        if ( hha_los_cache[i].valid && hha_los_cache[i].entNum == entNum ) {
            int age = cl.serverTime - hha_los_cache[i].checkTime;
            if ( age >= 0 && age < HHA_LOS_CACHE_MS ) {
                return hha_los_cache[i].los;
            }
            freeSlot = i;
            break;
        }
        if ( freeSlot < 0 && !hha_los_cache[i].valid ) freeSlot = i;
    }

    CM_BoxTrace( &tr, eye, chest, NULL, NULL, 0, CONTENTS_SOLID, 0 );
    if ( freeSlot < 0 ) freeSlot = 0;
    hha_los_cache[freeSlot].entNum    = entNum;
    hha_los_cache[freeSlot].checkTime = cl.serverTime;
    hha_los_cache[freeSlot].los       = ( tr.fraction >= 0.999f );
    hha_los_cache[freeSlot].valid     = qtrue;
    return hha_los_cache[freeSlot].los;
}

static void HHA_GetPredictedPos( const entityState_t *ent, const hha_config_t *cfg, vec3_t out ) {
    float dt = 0.0f;
    {
        float snapAgeMs = (float)( cl.serverTime - cl.snap.serverTime );
        if ( snapAgeMs < 0.0f )   snapAgeMs = 0.0f;
        if ( snapAgeMs > 200.0f ) snapAgeMs = 200.0f;
        dt += snapAgeMs * 0.001f;
    }
    if ( cfg->unlaggedSync && cl.snap.ping > 0 ) {
        float pingLead = (float)cl.snap.ping * 0.0005f;
        if ( pingLead > 0.15f ) pingLead = 0.15f;
        dt += pingLead;
    }
    if ( cfg->leadTime > 0.0f ) dt += cfg->leadTime;
    out[0] = ent->pos.trBase[0] + ent->pos.trDelta[0] * dt;
    out[1] = ent->pos.trBase[1] + ent->pos.trDelta[1] * dt;
    out[2] = ent->pos.trBase[2] + ent->pos.trDelta[2] * dt;
}

static int HHA_FindTarget( const hha_config_t *cfg, vec3_t bestDir, float *bestAngleOut ) {
    hha_candidate_t cands[HHA_MAX_CANDIDATES];
    int    ncands = 0, i, j;
    vec3_t forward;

    *bestAngleOut = 999.0f;

    if ( clc.state != CA_ACTIVE ) { HHA_SetTargetDist( 0.0f ); return -1; }
    if ( cl.snap.numEntities <= 0 ) { HHA_SetTargetDist( 0.0f ); return -1; }

    AngleVectors( cl.viewangles, forward, NULL, NULL );

    for ( i = 0; i < cl.snap.numEntities && ncands < HHA_MAX_CANDIDATES; i++ ) {
        entityState_t *ent = &cl.parseEntities[
            ( cl.snap.parseEntitiesNum + i ) & ( MAX_PARSE_ENTITIES - 1 ) ];
        float dx, dy, dz, distSq, dot, angle;
        vec3_t predFeet, toEnt;

        if ( ent->eType != ET_PLAYER ) continue;
        if ( ent->number == cl.snap.ps.clientNum ) continue;
        if ( ent->eFlags & EF_DEAD ) continue;

        HHA_GetPredictedPos( ent, cfg, predFeet );
        dx = predFeet[0] - cl.snap.ps.origin[0];
        dy = predFeet[1] - cl.snap.ps.origin[1];
        dz = predFeet[2] - cl.snap.ps.origin[2];
        distSq = dx*dx + dy*dy + dz*dz;

        if ( distSq < HHA_MIN_DIST * HHA_MIN_DIST ) continue;
        if ( distSq > cfg->maxDist * cfg->maxDist ) continue;

        toEnt[0] = dx; toEnt[1] = dy; toEnt[2] = dz;
        VectorNormalize( toEnt );

        dot = DotProduct( forward, toEnt );
        if ( dot >  1.0f ) dot =  1.0f;
        if ( dot < -1.0f ) dot = -1.0f;
        angle = acosf( dot ) * ( 180.0f / HHA_PI );
        if ( angle != angle ) continue;

        if ( ent->number == hha_lastTargetNum && angle < cfg->angle + 8.0f ) {
            angle *= 0.60f;
        }

        if ( angle < cfg->angle ) {
            cands[ncands].entNum  = ent->number;
            cands[ncands].angle   = angle;
            cands[ncands].distSq  = distSq;
            VectorCopy( toEnt, cands[ncands].dir );
            VectorCopy( predFeet, cands[ncands].feetPos );
            ncands++;
        }
    }

    for ( i = 0; i < ncands; i++ ) {
        for ( j = i + 1; j < ncands; j++ ) {
            if ( cands[j].angle < cands[i].angle ) {
                hha_candidate_t tmp = cands[i];
                cands[i] = cands[j];
                cands[j] = tmp;
            }
        }
    }

    for ( i = 0; i < ncands; i++ ) {
        qboolean ok = qtrue;
        if ( cfg->losEnabled && !cfg->hardLock ) {
            if ( hha_losChecksThisFrame >= HHA_LOS_BUDGET ) {
                ok = qfalse;
            } else {
                hha_losChecksThisFrame++;
                ok = HHA_HasLineOfSight( cands[i].entNum,
                                        cl.snap.ps.origin,
                                        cands[i].feetPos );
            }
        }
        if ( ok ) {
            *bestAngleOut = cands[i].angle;
            VectorCopy( cands[i].dir, bestDir );
            HHA_SetTargetDist( (float)sqrt( (double)cands[i].distSq ) );
            return cands[i].entNum;
        }
    }
    HHA_SetTargetDist( 0.0f );
    return -1;
}

static void CL_HandheldRespawnCheck( void ) {
    int      curSpawn, curHealth, curPmType, curTeam;
    qboolean respawned = qfalse;
    int      i;

    if ( !cl.snap.valid ) return;

    curSpawn  = cl.snap.ps.persistant[PERS_SPAWN_COUNT];
    curHealth = cl.snap.ps.stats[STAT_HEALTH];
    curPmType = cl.snap.ps.pm_type;
    curTeam   = cl.snap.ps.persistant[PERS_TEAM];

    if ( curTeam >= TEAM_SPECTATOR ) {
        hha_cachedValid    = qfalse;
        hha_cachedTarget   = -1;
        hha_lastTargetNum  = -1;
        hha_lastTargetAge  = 0;
        hha_lastSpawnCount = curSpawn;
        hha_lastHealth     = curHealth;
        hha_lastPmType     = curPmType;
        hha_firstCall      = qfalse;
        return;
    }

    if ( hha_firstCall ) {
        hha_firstCall      = qfalse;
        hha_lastSpawnCount = curSpawn;
        hha_lastHealth     = curHealth;
        hha_lastPmType     = curPmType;
        return;
    }

    if ( curSpawn != hha_lastSpawnCount ) {
        respawned = qtrue;
    } else if ( curHealth > 0 && hha_lastHealth <= 0 ) {
        respawned = qtrue;
    } else if ( curPmType != PM_DEAD && hha_lastPmType == PM_DEAD ) {
        respawned = qtrue;
    }

    if ( respawned ) {
        hha_cachedValid   = qfalse;
        hha_cachedTarget  = -1;
        hha_lastTargetNum = -1;
        hha_lastTargetAge = 0;
        for ( i = 0; i < HHA_LOS_CACHE_SIZE; i++ )
            hha_los_cache[i].valid = qfalse;
    }

    hha_lastSpawnCount = curSpawn;
    hha_lastHealth     = curHealth;
    hha_lastPmType     = curPmType;
}

static void CL_HandheldSearchTarget( void ) {
    if ( !hha_configValid ) {
        HHA_ReadConfig( &hha_cachedConfig );
        hha_configValid = qtrue;
    }
    if ( !hha_cachedConfig.enabled ) {
        hha_cachedValid  = qfalse;
        hha_cachedTarget = -1;
        return;
    }

    hha_losChecksThisFrame = 0;

    hha_cachedTarget = HHA_FindTarget( &hha_cachedConfig,
                                       hha_cachedDir, &hha_cachedAngle );
    hha_cachedValid  = qtrue;
    if ( hha_cachedTarget >= 0 ) {
        hha_lastTargetNum = hha_cachedTarget;
        hha_lastTargetAge = 0;
    } else if ( ++hha_lastTargetAge > hha_cachedConfig.stickyFrames ) {
        hha_lastTargetNum = -1;
    }
}

static void CL_HandheldInputCurve( void ) {
    hha_config_t *cfg = &hha_cachedConfig;
    int   *mx_raw, *my_raw;
    float  mag, friction = 1.0f;

    if ( !hha_configValid ) { HHA_ReadConfig( cfg ); hha_configValid = qtrue; }
    if ( !cfg->enabled ) return;

    mx_raw = &cl.mouseDx[cl.mouseIndex];
    my_raw = &cl.mouseDy[cl.mouseIndex];
    mag = sqrtf( (float)(*mx_raw * *mx_raw) + (float)(*my_raw * *my_raw) );
    if ( hha_cachedTarget >= 0 && mag > 0.0f && mag < HHA_FRICTION_MAX_MAG ) {
        friction = cfg->friction;
    }
    if ( *mx_raw != 0 ) {
        float s = ( *mx_raw < 0 ) ? -1.0f : 1.0f;
        float a = fabsf( (float)*mx_raw );
        float curved = powf( a, HHA_CURVE_EXP ) /
                       powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
        *mx_raw = (int)( s * curved * friction );
    }
    if ( *my_raw != 0 ) {
        float s = ( *my_raw < 0 ) ? -1.0f : 1.0f;
        float a = fabsf( (float)*my_raw );
        float curved = powf( a, HHA_CURVE_EXP ) /
                       powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
        *my_raw = (int)( s * curved * friction );
    }
}

static void CL_HandheldAimMagnetism( usercmd_t *cmd ) {
    hha_config_t *cfg = &hha_cachedConfig;
    vec3_t forward, targetAngles;
    float  dot, currentAngle, yawDiff, pitchDiff, strength;
    float  magYaw, magPitch, pullYaw, pullPitch, cap;
    qboolean firing, inSnap;

    if ( !hha_configValid ) { HHA_ReadConfig( cfg ); hha_configValid = qtrue; }
    if ( !cfg->enabled ) return;
    if ( clc.state != CA_ACTIVE ) return;
    if ( !hha_cachedValid || hha_cachedTarget < 0 ) return;

    AngleVectors( cl.viewangles, forward, NULL, NULL );
    dot = DotProduct( forward, hha_cachedDir );
    if ( dot >  1.0f ) dot =  1.0f;
    if ( dot < -1.0f ) dot = -1.0f;
    currentAngle = acosf( dot ) * ( 180.0f / HHA_PI );
    if ( currentAngle != currentAngle ) return;

    if ( cfg->hardLock ) {
        vectoangles( hha_cachedDir, targetAngles );

        while ( targetAngles[YAW] > 180.0f )  targetAngles[YAW]  -= 360.0f;
        while ( targetAngles[YAW] < -180.0f ) targetAngles[YAW]  += 360.0f;
        if ( targetAngles[PITCH] < -180.0f )  targetAngles[PITCH] += 360.0f;

        if ( targetAngles[PITCH] >  HHA_PITCH_LIMIT ) targetAngles[PITCH] =  HHA_PITCH_LIMIT;
        if ( targetAngles[PITCH] < -HHA_PITCH_LIMIT ) targetAngles[PITCH] = -HHA_PITCH_LIMIT;

        cl.viewangles[YAW]   = targetAngles[YAW];
        cl.viewangles[PITCH] = targetAngles[PITCH];
        return;
    }

    if ( currentAngle > cfg->angle ) return;

    firing = ( cmd && ( cmd->buttons & BUTTON_ATTACK ) && cfg->fireEnabled );
    if ( firing ) { magYaw = cfg->fireYaw; magPitch = cfg->firePitch; }
    else           { magYaw = cfg->strengthYaw; magPitch = cfg->strengthPitch; }

    inSnap = ( currentAngle <= cfg->snapAngle && cfg->snapAngle > 0.0f );
    if ( inSnap ) { magYaw *= 2.0f; magPitch *= 2.0f; }

    vectoangles( hha_cachedDir, targetAngles );
    yawDiff   = targetAngles[YAW]   - cl.viewangles[YAW];
    pitchDiff = targetAngles[PITCH] - cl.viewangles[PITCH];
    while ( yawDiff   >  180.0f ) yawDiff   -= 360.0f;
    while ( yawDiff   < -180.0f ) yawDiff   += 360.0f;
    while ( pitchDiff >  180.0f ) pitchDiff -= 360.0f;
    while ( pitchDiff < -180.0f ) pitchDiff += 360.0f;

    if ( currentAngle <= cfg->falloff ) {
        strength = 1.0f;
    } else {
        strength = 1.0f - ( currentAngle - cfg->falloff ) /
                          ( cfg->angle - cfg->falloff );
        if ( strength < 0.0f ) strength = 0.0f;
    }

    pullYaw   = magYaw   * strength;
    pullPitch = magPitch * strength;
    cap = inSnap ? HHA_PULL_CAP_SNAP : HHA_PULL_CAP_NORMAL;
    if ( pullYaw   >  cap ) pullYaw   =  cap;
    if ( pullYaw   < -cap ) pullYaw   = -cap;
    if ( pullPitch >  cap ) pullPitch =  cap;
    if ( pullPitch < -cap ) pullPitch = -cap;

    cl.viewangles[YAW]   += yawDiff   * pullYaw;
    cl.viewangles[PITCH] += pitchDiff * pullPitch;

    if ( cl.viewangles[YAW] >  180.0f ) cl.viewangles[YAW]   -= 360.0f;
    if ( cl.viewangles[YAW] < -180.0f ) cl.viewangles[YAW]   += 360.0f;
    if ( cl.viewangles[PITCH] >  HHA_PITCH_LIMIT ) {
        cl.viewangles[PITCH] =  HHA_PITCH_LIMIT;
        if ( hha_lastPitchClampLog == 0 ) {
            HHA_Log("Pitch clamped to +%.1f (aim-assist)", HHA_PITCH_LIMIT);
            hha_lastPitchClampLog = cl.serverTime;
        }
    }
    if ( cl.viewangles[PITCH] < -HHA_PITCH_LIMIT ) {
        cl.viewangles[PITCH] = -HHA_PITCH_LIMIT;
        if ( hha_lastPitchClampLog == 0 ) {
            HHA_Log("Pitch clamped to -%.1f (aim-assist)", HHA_PITCH_LIMIT);
            hha_lastPitchClampLog = cl.serverTime;
        }
    }
    if ( hha_lastPitchClampLog != 0 && cl.serverTime - hha_lastPitchClampLog > 2000 ) {
        hha_lastPitchClampLog = 0;
    }
}

static int HHA_ComputeAimHash( void ) {
    int h = 0;
    h ^= ( Cvar_VariableIntegerValue("cg_handheldAimAssist")              & 1 ) << 0;
    h ^= ( Cvar_VariableIntegerValue("cg_handheldAimAssistFire")          & 1 ) << 1;
    h ^= ( Cvar_VariableIntegerValue("cg_handheldAimAssistHardLock")      & 1 ) << 2;
    h ^= ( Cvar_VariableIntegerValue("cg_handheldAimAssistLOS")           & 1 ) << 3;
    h ^= ( Cvar_VariableIntegerValue("cg_handheldAimAssistInterpolate")   & 1 ) << 4;
    h ^= ( Cvar_VariableIntegerValue("cg_handheldAimAssistUnlaggedSync")  & 1 ) << 5;
    h ^= ( (int)( Cvar_VariableValue("cg_handheldAimAssistAngle")    * 10.0f ) & 0x3FF ) << 6;
    h ^= ( (int)( Cvar_VariableValue("cg_handheldAimAssistStrength") * 100.0f ) & 0x1FF ) << 16;
    h ^= ( Cvar_VariableIntegerValue("cg_handheldAimAssistSticky")        & 0x3F ) << 25;
    return h;
}

static void HHA_ApplyPresetValues( int preset ) {
    if ( preset == 1 ) {
        Cvar_Set("cg_handheldAimAssist",             "1");
        Cvar_Set("cg_handheldAimAssistFire",         "1");
        Cvar_Set("cg_handheldAimAssistAngle",        "89");
        Cvar_Set("cg_handheldAimAssistStrength",     "1.20");
        Cvar_Set("cg_handheldAimAssistFriction",     "0.50");
        Cvar_Set("cg_handheldAimAssistPitch",        "1.50");
        Cvar_Set("cg_handheldAimAssistSnapAngle",    "15");
        Cvar_Set("cg_handheldAimAssistSticky",       "30");
        Cvar_Set("cg_handheldAimAssistMaxDist",      "8000");
        Cvar_Set("cg_handheldAimAssistInterpolate",  "1");
        Cvar_Set("cg_handheldAimAssistUnlaggedSync", "0");
        Cvar_Set("cg_handheldAimAssistLead",         "0");
        Cvar_Set("cg_handheldAimAssistLOS",          "0");
        Cvar_Set("cg_handheldAimAssistHardLock",     "1");
        Cvar_Set("cg_handheldAimAssistZoom",         "1");
        Cvar_Set("cg_handheldAimAssistZoomNear",     "80");
        Cvar_Set("cg_handheldAimAssistZoomFar",      "1200");
        Cvar_Set("cg_handheldAimAssistZoomFov",      "30");
        Cvar_Set("cg_handheldAimAssistZoomSpeed",    "25");
    } else if ( preset == 2 ) {
        Cvar_Set("cg_handheldAimAssist",             "1");
        Cvar_Set("cg_handheldAimAssistFire",         "1");
        Cvar_Set("cg_handheldAimAssistAngle",        "28");
        Cvar_Set("cg_handheldAimAssistStrength",     "0.55");
        Cvar_Set("cg_handheldAimAssistFriction",     "0.85");
        Cvar_Set("cg_handheldAimAssistPitch",        "0.80");
        Cvar_Set("cg_handheldAimAssistSnapAngle",    "5");
        Cvar_Set("cg_handheldAimAssistSticky",       "15");
        Cvar_Set("cg_handheldAimAssistMaxDist",      "3000");
        Cvar_Set("cg_handheldAimAssistInterpolate",  "1");
        Cvar_Set("cg_handheldAimAssistUnlaggedSync", "0");
        Cvar_Set("cg_handheldAimAssistLead",         "0");
        Cvar_Set("cg_handheldAimAssistLOS",          "1");
        Cvar_Set("cg_handheldAimAssistHardLock",     "0");
        Cvar_Set("cg_handheldAimAssistZoom",         "1");
        Cvar_Set("cg_handheldAimAssistZoomNear",     "100");
        Cvar_Set("cg_handheldAimAssistZoomFar",      "600");
        Cvar_Set("cg_handheldAimAssistZoomFov",      "40");
        Cvar_Set("cg_handheldAimAssistZoomSpeed",    "15");
    } else if ( preset == 3 ) {
        Cvar_Set("cg_handheldAimAssist",             "1");
        Cvar_Set("cg_handheldAimAssistFire",         "1");
        Cvar_Set("cg_handheldAimAssistAngle",        "89");
        Cvar_Set("cg_handheldAimAssistStrength",     "1.20");
        Cvar_Set("cg_handheldAimAssistFriction",     "0.50");
        Cvar_Set("cg_handheldAimAssistPitch",        "1.50");
        Cvar_Set("cg_handheldAimAssistSnapAngle",    "15");
        Cvar_Set("cg_handheldAimAssistSticky",       "30");
        Cvar_Set("cg_handheldAimAssistMaxDist",      "8000");
        Cvar_Set("cg_handheldAimAssistInterpolate",  "1");
        Cvar_Set("cg_handheldAimAssistUnlaggedSync", "0");
        Cvar_Set("cg_handheldAimAssistLead",         "0");
        Cvar_Set("cg_handheldAimAssistLOS",          "0");
        Cvar_Set("cg_handheldAimAssistHardLock",     "1");
        Cvar_Set("cg_handheldAimAssistZoom",         "1");
        Cvar_Set("cg_handheldAimAssistZoomNear",     "80");
        Cvar_Set("cg_handheldAimAssistZoomFar",      "1200");
        Cvar_Set("cg_handheldAimAssistZoomFov",      "30");
        Cvar_Set("cg_handheldAimAssistZoomSpeed",    "25");
    }
}

static void HHA_EnsurePresetConsistency( void ) {
    int curPreset = Cvar_VariableIntegerValue("cg_handheldAimPreset");
    int curHash   = HHA_ComputeAimHash();

    if ( hha_lastPreset == -2 ) {
        hha_lastPreset  = curPreset;
        hha_lastAimHash = curHash;
        HHA_Log("Startup: preset=%d hash=0x%X", curPreset, curHash);
        return;
    }
    if ( curPreset != hha_lastPreset ) {
        HHA_Log("Preset change %d -> %d", hha_lastPreset, curPreset);
        hha_lastPreset = curPreset;
        if ( curPreset > 0 ) HHA_ApplyPresetValues( curPreset );
        hha_lastAimHash = HHA_ComputeAimHash();
        return;
    }
    if ( curPreset > 0 && curHash != hha_lastAimHash ) {
        HHA_Log("Manual sub-cvar change -> Preset 0 (Custom)");
        Cvar_Set("cg_handheldAimPreset", "0");
        hha_lastPreset  = 0;
        hha_lastAimHash = curHash;
    }
}

static void HHA_Cmd_AimDump( void ) {
    Com_Printf( "===== Handheld Aim Assist =====\n" );
    Com_Printf( "  Preset        : %d (0=Custom 1=Online 2=Offline 3=Aimbot)\n", Cvar_VariableIntegerValue("cg_handheldAimPreset") );
    Com_Printf( "  Enabled       : %d\n", Cvar_VariableIntegerValue("cg_handheldAimAssist") );
    Com_Printf( "  HardLock      : %d\n", Cvar_VariableIntegerValue("cg_handheldAimAssistHardLock") );
    Com_Printf( "  Angle         : %.2f\n", Cvar_VariableValue("cg_handheldAimAssistAngle") );
    Com_Printf( "  Strength      : %.2f\n", Cvar_VariableValue("cg_handheldAimAssistStrength") );
    Com_Printf( "  MaxDist       : %.2f\n", Cvar_VariableValue("cg_handheldAimAssistMaxDist") );
    Com_Printf( "  TargetDist    : %.1f\n", Cvar_VariableValue("cg_handheldAimAssistTargetDist") );
    Com_Printf( "  Log enabled   : %d\n", Cvar_VariableIntegerValue("cg_handheldLog") );
    Com_Printf( "===============================\n" );
    HHA_Log("aim_dump: preset=%d hardLock=%d targetDist=%.1f",
            Cvar_VariableIntegerValue("cg_handheldAimPreset"),
            Cvar_VariableIntegerValue("cg_handheldAimAssistHardLock"),
            Cvar_VariableValue("cg_handheldAimAssistTargetDist"));
}

static void HHA_Cmd_AimSync( void ) {
    int p = Cvar_VariableIntegerValue("cg_handheldAimPreset");
    if ( p == 0 ) { Com_Printf( "Aim-Assist: Custom-Preset aktiv.\n" ); return; }
    HHA_ApplyPresetValues( p );
    hha_lastAimHash = HHA_ComputeAimHash();
    HHA_Log("aim_sync: preset %d re-applied", p);
    Com_Printf( "Aim-Assist: Preset %d wurde angewendet.\n", p );
}
/* ============================================================ */
"""

    mouse_pat = re.compile(
        r'(void\s+CL_MouseMove\s*\(\s*usercmd_t\s*\*\s*cmd\s*\)\s*\{)')
    if not mouse_pat.search(content):
        print("[WARN] CL_MouseMove not found")
        return False
    content = mouse_pat.sub(
        lambda m: helper_code + "\n" + m.group(1) + "\n\tCL_HandheldInputCurve();",
        content, count=1)

    joy_pat = re.compile(r'(\n[ \t]*CL_JoystickMove\s*\(\s*&\s*cmd\s*\)\s*;)')
    if not joy_pat.search(content):
        print("[WARN] CL_JoystickMove not found")
        return False
    joy_repl = (
        r'\1'
        r'\n\n\t/* v14.1: Target-Scan mit frischen cl.viewangles */\n'
        r'\tCL_HandheldRespawnCheck();\n'
        r'\tCL_HandheldSearchTarget();\n'
        r'\tCL_HandheldAimMagnetism( &cmd );'
    )
    content = joy_pat.sub(joy_repl, content, count=1)
    print("[PATCHED] Respawn-Check + Target-Scan nach CL_JoystickMove")

    createcmd_pat = re.compile(
        r'(usercmd_t\s+CL_CreateCmd\s*\(\s*void\s*\)\s*\{)')
    if not createcmd_pat.search(content):
        print("[WARN] CL_CreateCmd not found")
    else:
        content = createcmd_pat.sub(
            r'\1\n\tHHA_EnsurePresetConsistency();\n',
            content, count=1)
        print("[PATCHED] Preset-Consistency in CL_CreateCmd")

    cmdreg_anchor = '\tCmd_AddCommand ("centerview",IN_CenterView);'
    if cmdreg_anchor in content:
        content = content.replace(
            cmdreg_anchor,
            cmdreg_anchor + "\n"
            '\tCmd_AddCommand ("aim_dump", HHA_Cmd_AimDump);\n'
            '\tCmd_AddCommand ("aim_sync", HHA_Cmd_AimSync);',
            1)
        print("[PATCHED] aim_dump/aim_sync commands registered")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Aim assist v14.1 in {target_file}")
    return True


def patch_cl_main_namerotator():
    target_file = os.path.join("code", "client", "cl_main.c")
    if not os.path.exists(target_file):
        print("[WARN] cl_main.c not found")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "HHA_NameRotator" in content:
        print("[SKIP] Name rotator already present")
        return True

    helper_code = r"""
/* ============================================================
 * [PATCHED v13.8] Name Color Rotator (Respawn-Triggered)
 * ============================================================ */
static int      hha_nameLastSpawnCount = -1;
static int      hha_nameLastHealth     = -999;
static int      hha_nameLastPmType     = -1;
static qboolean hha_nameFirstCall      = qtrue;

static int  hha_nameCounter = 0;
static char hha_nameLastSet[128] = {0};
static char hha_nameBaseText[64] = {0};

static qboolean HHA_NameRotator_JustRespawned( void ) {
    int      curSpawn, curHealth, curPmType, curTeam;
    qboolean respawned = qfalse;

    if ( !cl.snap.valid ) {
        return qfalse;
    }

    curSpawn  = cl.snap.ps.persistant[PERS_SPAWN_COUNT];
    curHealth = cl.snap.ps.stats[STAT_HEALTH];
    curPmType = cl.snap.ps.pm_type;
    curTeam   = cl.snap.ps.persistant[PERS_TEAM];

    if ( curTeam >= TEAM_SPECTATOR ) {
        hha_nameFirstCall      = qfalse;
        hha_nameLastSpawnCount = curSpawn;
        hha_nameLastHealth     = curHealth;
        hha_nameLastPmType     = curPmType;
        return qfalse;
    }

    if ( hha_nameFirstCall ) {
        hha_nameFirstCall      = qfalse;
        hha_nameLastSpawnCount = curSpawn;
        hha_nameLastHealth     = curHealth;
        hha_nameLastPmType     = curPmType;
        return qfalse;
    }

    if ( curSpawn != hha_nameLastSpawnCount ) {
        respawned = qtrue;
    } else if ( curHealth > 0 && hha_nameLastHealth <= 0 ) {
        respawned = qtrue;
    } else if ( curPmType != PM_DEAD && hha_nameLastPmType == PM_DEAD ) {
        respawned = qtrue;
    }

    hha_nameLastSpawnCount = curSpawn;
    hha_nameLastHealth     = curHealth;
    hha_nameLastPmType     = curPmType;

    if ( respawned && curHealth > 0 && curPmType != PM_DEAD ) {
        return qtrue;
    }
    return qfalse;
}

static void HHA_StripColors(const char *src, char *dst, int dstsize) {
    int i = 0, j = 0;
    if (!src || !dst || dstsize <= 0) { if (dst) dst[0] = 0; return; }
    while (src[i] && j < dstsize - 1) {
        if (src[i] == '^' && src[i+1] && src[i+1] != '^') { i += 2; continue; }
        if (src[i] == '^' && src[i+1] == '^') { dst[j++] = '^'; i += 2; continue; }
        dst[j++] = src[i++];
    }
    dst[j] = 0;
}

static void HHA_BuildColoredName(const char *text, int scheme, int offset,
                                 char *out, int outsize) {
    int len, i, j = 0;
    if (!text || !out || outsize < 4) { if (out) out[0] = 0; return; }
    out[0] = 0;
    len = (int)strlen(text);
    for (i = 0; i < len && j + 3 < outsize; i++) {
        int colorIdx;
        switch (scheme) {
            case 0:  colorIdx = ((i + offset) % 7) + 1; break;
            case 1:  colorIdx = ((offset) % 7) + 1; break;
            case 2:  colorIdx = ((i + offset) & 1) ? 1 : 4; break;
            case 3:  colorIdx = ((i + offset) % 3) ? 7 : 1; break;
            default: colorIdx = 7; break;
        }
        out[j++] = '^';
        out[j++] = (char)('0' + colorIdx);
        out[j++] = text[i];
    }
    out[j] = 0;
}

static void HHA_NameRotator( void ) {
    const char *nameStr;
    char        curName[128];
    char        newName[128];
    int         rotate, scheme;

    rotate = Cvar_VariableIntegerValue("cg_handheldNameRotate");
    if (!rotate) return;

    if ( !HHA_NameRotator_JustRespawned() ) return;

    nameStr = Cvar_VariableString("name");
    if (!nameStr) return;
    Q_strncpyz(curName, nameStr, sizeof(curName));

    if (strcmp(curName, hha_nameLastSet) != 0) {
        HHA_StripColors(curName, hha_nameBaseText, sizeof(hha_nameBaseText));
    }
    if (!hha_nameBaseText[0]) {
        HHA_StripColors(curName, hha_nameBaseText, sizeof(hha_nameBaseText));
        if (!hha_nameBaseText[0]) return;
    }

    hha_nameCounter++;
    scheme = Cvar_VariableIntegerValue("cg_handheldNameScheme");
    HHA_BuildColoredName(hha_nameBaseText, scheme, hha_nameCounter,
                         newName, sizeof(newName));
    Cvar_Set("name", newName);
    Q_strncpyz(hha_nameLastSet, newName, sizeof(hha_nameLastSet));
}
/* ============================================================ */

"""

    frame_anchor = "void CL_Frame ( int msec ) {"
    if frame_anchor not in content:
        print("[WARN] CL_Frame anchor not found")
        return False
    content = content.replace(frame_anchor, helper_code + "\n" + frame_anchor, 1)

    call_anchor = "\t// see if we need to update any userinfo\n\tCL_CheckUserinfo();"
    if call_anchor not in content:
        print("[WARN] CL_CheckUserinfo anchor not found")
        return False
    content = content.replace(call_anchor, call_anchor + "\n\n\tHHA_NameRotator();", 1)

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Name rotator in cl_main.c (v13.8)")
    return True


def patch_cl_console_chatprefill():
    """v14.4: Chat-Prefill robuster. Hakt alle Message-Mode-Funktionen."""
    target_file = os.path.join("code", "client", "cl_console.c")
    if not os.path.exists(target_file):
        print("[WARN] cl_console.c not found")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "HHA_CHATPREFIX_V2" in content:
        print("[SKIP] Chat prefill v2 already present")
        return True

    old_block = (
        "\n\t/* [PATCHED v13.5] Automatischer Chat-Prefill */\n"
        "\t{\n"
        "\t\tconst char *hha_prefix = Cvar_VariableString(\"cg_handheldChatPrefix\");\n"
        "\t\tif (hha_prefix && *hha_prefix) {\n"
        "\t\t\tQ_strncpyz(chatField.buffer, hha_prefix, sizeof(chatField.buffer));\n"
        "\t\t\tchatField.cursor = (int)strlen(chatField.buffer);\n"
        "\t\t\tchatField.scroll = 0;\n"
        "\t\t}\n"
        "\t}\n"
    )
    while old_block in content:
        content = content.replace(old_block, "", 1)

    helper = r'''
/* ============================================================
 * [PATCHED v14.4] Chat-Prefill Helper
 * HHA_CHATPREFIX_V2
 * ============================================================ */
static void HHA_ApplyChatPrefix( void ) {
    const char *prefix = Cvar_VariableString("cg_handheldChatPrefix");
    if ( !prefix || !*prefix ) return;
    if ( chatField.buffer[0] != '\0' ) return;
    Q_strncpyz( chatField.buffer, prefix, sizeof( chatField.buffer ) );
    chatField.cursor = (int)strlen( chatField.buffer );
    chatField.scroll = 0;
}
'''

    inc_matches = list(re.finditer(r'#include\s+"[^"]+"\s*\n', content))
    if inc_matches:
        pos = inc_matches[-1].end()
        content = content[:pos] + "\n" + helper + "\n" + content[pos:]
    else:
        content = helper + "\n" + content

    pat = re.compile(
        r'(chatField\.widthInChars\s*=\s*\d+\s*;[\s\n]*)'
        r'(Key_SetCatcher\s*\(\s*Key_GetCatcher\s*\(\s*\)\s*\^\s*'
        r'KEYCATCH_MESSAGE\s*\)\s*;)'
    )

    def _hook(m):
        return m.group(1) + "\tHHA_ApplyChatPrefix(); /* HHA_CHATPREFIX_V2 */\n\n\t" + m.group(2)

    content, n = pat.subn(_hook, content)
    print(f"[PATCHED] Chat prefill v14.4 in {n} Funktion(en)")

    if n == 0:
        print("[WARN] Chat prefill: kein Hook eingebaut - Anker nicht gefunden")
        return False

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_cg_view():
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_view.c" in files:
            target_file = os.path.join(root, "cg_view.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_view.c not found")
        return False

    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    zoom_helper = r"""
/* ============================================================
 * [PATCHED v13.5] Dynamic Zoom + Auto-Switch (cgame-VM)
 * ============================================================ */
static float HHA_CvarValueCG( const char *name ) {
    char buf[64];
    buf[0] = 0;
    trap_Cvar_VariableStringBuffer( name, buf, sizeof(buf) );
    return (float)atof( buf );
}

static float cg_hhaZoomCurrent  = 0.0f;
static int   cg_hhaZoomLastTime = 0;
static int   cg_hhaZoomLastSpawnCount = -1;

static float CG_HandheldScanNearestTarget( void ) {
    float  bestDistSq = 0.0f;
    vec3_t forward, toEnt;
    int    i;
    entityState_t *best = NULL;

    if ( !cg.snap ) return 0.0f;
    if ( cg.snap->ps.stats[STAT_HEALTH] <= 0 ) return 0.0f;
    if ( cg.snap->ps.persistant[PERS_TEAM] >= TEAM_SPECTATOR ) return 0.0f;
    if ( cg.snap->numEntities <= 0 ) return 0.0f;

    AngleVectors( cg.refdefViewAngles, forward, NULL, NULL );

    for ( i = 0; i < cg.snap->numEntities; i++ ) {
        entityState_t *ent = &cg.snap->entities[i];
        float dx, dy, dz, distSq, dot;
        vec3_t entPos;

        if ( ent->eType != ET_PLAYER ) continue;
        if ( ent->number == cg.snap->ps.clientNum ) continue;
        if ( ent->eFlags & EF_DEAD ) continue;

        VectorCopy( ent->pos.trBase, entPos );
        dx = entPos[0] - cg.refdef.vieworg[0];
        dy = entPos[1] - cg.refdef.vieworg[1];
        dz = entPos[2] - cg.refdef.vieworg[2];
        distSq = dx*dx + dy*dy + dz*dz;

        if ( distSq < 48.0f * 48.0f ) continue;
        if ( distSq > 8000.0f * 8000.0f ) continue;

        toEnt[0] = dx; toEnt[1] = dy; toEnt[2] = dz;
        VectorNormalize( toEnt );

        dot = DotProduct( forward, toEnt );
        if ( dot < 0.3f ) continue;

        if ( best == NULL || distSq < bestDistSq ) {
            best = ent;
            bestDistSq = distSq;
        }
    }

    if ( best == NULL ) return 0.0f;
    return (float)sqrt( (double)bestDistSq );
}

static void CG_HandheldApplyZoom( void ) {
    float    nearDist, farDist, targetFov, speed;
    float    dist, targetZoom, deltaTime, factor, lerpRate;
    float    baseFov, newFov, x;
    int      curSpawn;
    float    enabled;

    curSpawn = cg.predictedPlayerState.persistant[PERS_SPAWN_COUNT];
    if ( curSpawn != cg_hhaZoomLastSpawnCount ) {
        cg_hhaZoomLastSpawnCount = curSpawn;
        cg_hhaZoomCurrent  = 0.0f;
        cg_hhaZoomLastTime = cg.time;
    }

    if ( cg.zoomed ) return;
    enabled = HHA_CvarValueCG("cg_handheldAimAssistZoom");
    if ( enabled == 0.0f || cg.renderingThirdPerson ||
         cg.predictedPlayerState.pm_type == PM_INTERMISSION ||
         cg.snap->ps.stats[STAT_HEALTH] <= 0 ||
         cg.snap->ps.persistant[PERS_TEAM] >= TEAM_SPECTATOR ) {
        cg_hhaZoomCurrent  = 0.0f;
        cg_hhaZoomLastTime = cg.time;
        return;
    }

    dist      = CG_HandheldScanNearestTarget();
    nearDist  = HHA_CvarValueCG("cg_handheldAimAssistZoomNear");
    farDist   = HHA_CvarValueCG("cg_handheldAimAssistZoomFar");
    targetFov = HHA_CvarValueCG("cg_handheldAimAssistZoomFov");
    speed     = HHA_CvarValueCG("cg_handheldAimAssistZoomSpeed");

    if ( nearDist  <   50.0f ) nearDist  =   50.0f;
    if ( nearDist  > 1500.0f ) nearDist  = 1500.0f;
    if ( farDist   <  300.0f ) farDist   =  300.0f;
    if ( farDist   > 4000.0f ) farDist   = 4000.0f;
    if ( targetFov <   25.0f ) targetFov =   25.0f;
    if ( targetFov >   85.0f ) targetFov =   85.0f;
    if ( speed     <    1.0f ) speed     =    1.0f;
    if ( speed     >   25.0f ) speed     =   25.0f;
    if ( farDist <= nearDist ) farDist   = nearDist + 1.0f;

    if ( dist <= 0.0f || dist <= nearDist ) targetZoom = 0.0f;
    else if ( dist >= farDist )             targetZoom = 1.0f;
    else targetZoom = ( dist - nearDist ) / ( farDist - nearDist );

    deltaTime = (float)( cg.time - cg_hhaZoomLastTime ) * 0.001f;
    cg_hhaZoomLastTime = cg.time;
    if ( deltaTime <= 0.0f || deltaTime > 0.1f ) deltaTime = 0.016f;

    lerpRate = speed * 2.5f;
    factor   = 1.0f - (float)exp( -(double)( lerpRate * deltaTime ) );
    if ( factor < 0.0f ) factor = 0.0f;
    if ( factor > 1.0f ) factor = 1.0f;
    cg_hhaZoomCurrent += ( targetZoom - cg_hhaZoomCurrent ) * factor;

    if ( targetZoom <= 0.0f && cg_hhaZoomCurrent < 0.0005f ) cg_hhaZoomCurrent = 0.0f;
    if ( cg_hhaZoomCurrent > 0.0005f ) {
        baseFov = cg.refdef.fov_x;
        newFov  = baseFov + ( targetFov - baseFov ) * cg_hhaZoomCurrent;
        if ( newFov <   1.0f ) newFov =   1.0f;
        if ( newFov > 160.0f ) newFov = 160.0f;
        cg.refdef.fov_x = newFov;
        x = cg.refdef.width / tan( newFov / 360.0f * M_PI );
        cg.refdef.fov_y = atan2( (float)cg.refdef.height, x ) * 360.0f / M_PI;
    }
}

static int cg_hhaLastSwitchTime = 0;
static int cg_hhaSwitchLastSpawnCount = -1;

static int CG_HandheldGetAmmo( playerState_t *ps, int weapon ) {
    if ( weapon <= WP_NONE || weapon >= WP_NUM_WEAPONS ) return 0;
    return ps->ammo[weapon];
}

static int CG_HandheldGetReserve( playerState_t *ps, int weapon ) {
    int clip;
    if ( weapon <= WP_NONE || weapon >= WP_NUM_WEAPONS ) return 0;
    clip = bg_weaponlist[weapon].clip;
    if ( clip <= 0 || clip >= WP_SEC_PISTOL ) return 0;
    return ps->ammo[clip];
}

static qboolean CG_HandheldHasAmmo( playerState_t *ps, int weapon ) {
    if ( CG_HandheldGetAmmo( ps, weapon ) > 0 ) return qtrue;
    if ( CG_HandheldGetReserve( ps, weapon ) > 0 ) return qtrue;
    if ( ( ps->stats[STAT_FLAGS] & SF_SEC_PISTOL ) &&
         bg_weaponlist[weapon].wp_sort == WPS_PISTOL ) {
        if ( ps->ammo[WP_AKIMBO] > 0 ) return qtrue;
    }
    return qfalse;
}

static void CG_HandheldAutoSwitch( void ) {
    playerState_t *ps;
    int curWeapon, i;
    int best = -1, bestScore = -1;
    int curSpawn;

    if ( !cg.snap ) return;
    if ( HHA_CvarValueCG("cg_handheldAutoSwitch") == 0.0f ) return;

    ps = &cg.predictedPlayerState;

    curSpawn = ps->persistant[PERS_SPAWN_COUNT];
    if ( curSpawn != cg_hhaSwitchLastSpawnCount ) {
        cg_hhaSwitchLastSpawnCount = curSpawn;
        cg_hhaLastSwitchTime = 0;
    }

    if ( ps->pm_type == PM_INTERMISSION ) return;
    if ( ps->pm_type == PM_DEAD ) return;
    if ( ps->stats[STAT_HEALTH] <= 0 ) return;
    if ( ps->persistant[PERS_TEAM] >= TEAM_SPECTATOR ) return;
    if ( cg.time - cg_hhaLastSwitchTime < 1000 ) return;

    curWeapon = ps->weapon;
    if ( curWeapon <= WP_NONE || curWeapon >= WP_NUM_WEAPONS ) return;
    if ( curWeapon == WP_KNIFE ) return;
    if ( curWeapon == WP_GATLING ) return;
    if ( ( curWeapon == WP_DYNAMITE || curWeapon == WP_MOLOTOV ) &&
         ps->ammo[curWeapon] > 0 ) return;

    if ( CG_HandheldHasAmmo( ps, curWeapon ) ) return;

    for ( i = 1; i < WP_NUM_WEAPONS; i++ ) {
        int score;
        if ( i == curWeapon ) continue;
        if ( i == WP_KNIFE ) continue;
        if ( i == WP_GATLING ) continue;
        if ( i == WP_DYNAMITE || i == WP_MOLOTOV ) continue;
        if ( !(ps->stats[STAT_WEAPONS] & (1 << i)) ) continue;
        if ( !CG_HandheldHasAmmo( ps, i ) ) continue;

        score = CG_HandheldGetAmmo( ps, i ) * 10 + CG_HandheldGetReserve( ps, i );
        if ( score > bestScore ) { bestScore = score; best = i; }
    }

    if ( best >= 0 && best != curWeapon ) {
        cg.weaponSelect      = best;
        cg.weaponSelectTime  = cg.time;
        cg_hhaLastSwitchTime = cg.time;
    }
}
/* ============================================================ */

"""

    if "CG_HandheldApplyZoom" not in content:
        calc_anchor_pat = re.compile(r'(/\*\s*\n=+\s*\nCG_CalcFov\s*\n)')
        if not calc_anchor_pat.search(content):
            print("[WARN] CG_CalcFov comment anchor not found")
            return False
        content = calc_anchor_pat.sub(lambda m: zoom_helper + m.group(1),
                                      content, count=1)

        fov_set_pat = re.compile(
            r'(cg\.refdef\.fov_x\s*=\s*fov_x\s*;\s*\n'
            r'\s*cg\.refdef\.fov_y\s*=\s*fov_y\s*;)')
        if not fov_set_pat.search(content):
            print("[WARN] FOV assignment anchor not found")
            return False
        content = fov_set_pat.sub(
            r'\1\n\n\tCG_HandheldApplyZoom();',
            content, count=1)
        print("[PATCHED] Dynamic Zoom hook in CG_CalcFov")

    setucv_pat = re.compile(
        r'(\n[ \t]*trap_SetUserCmdValue\s*\(\s*cg\.weaponSelect\s*,\s*cg\.zoomSensitivity\s*\)\s*;)')
    if setucv_pat.search(content):
        content = setucv_pat.sub(
            r'\n\n\tCG_HandheldAutoSwitch();\n\1',
            content, count=1)
        print("[PATCHED] Auto-Switch hook before trap_SetUserCmdValue()")
    else:
        print("[WARN] trap_SetUserCmdValue anchor not found")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_cg_hitmarker():
    """v14.3: Hitmarker X-Form + Richtungs-Damage-Indicator (Ring-Dots)."""
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_draw.c" in files:
            target_file = os.path.join(root, "cg_draw.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_draw.c not found")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "HHA_HITMARKER_V3" in content:
        print("[SKIP] Hitmarker/Damage-Indicator v14.3 bereits gepatcht")
        return True

    for old_marker in ["HHA_HITMARKER_V2",
                       "[PATCHED v14.2] Hitmarker",
                       "[PATCHED v13.5] Hitmarker"]:
        if old_marker in content:
            start_marker = "/* ============================================================\n"
            idx = content.find(old_marker)
            if idx >= 0:
                start = content.rfind(start_marker, 0, idx)
                if start < 0:
                    start = idx - 60
                end_marker = "/* ============================================================ */"
                end = content.find(end_marker, idx)
                if end >= 0:
                    end += len(end_marker)
                    content = content[:start] + content[end:]
    content = content.replace('\n\n\tCG_HandheldDrawOverlays();\n', '\n')
    content = content.replace('\n\n\tCG_HandheldDrawOverlays();', '')
    content = content.replace('\n\n\t/* HHA_HITMARKER_V2 */\n\tCG_HandheldDrawOverlays();', '')

    hitmarker_code = r'''

/* ============================================================
 * [PATCHED v14.3] Hitmarker + Damage-Indicator (Ring-Dots)
 * HHA_HITMARKER_V3
 * ============================================================ */
#include <math.h>

static int cg_hhaHitMarkerTime = 0;
static int cg_hhaHitMarkerWasKill = 0;

void CG_RegisterHitMarker( void ) {
    cg_hhaHitMarkerTime = cg.time;
    cg_hhaHitMarkerWasKill = 0;
}

void CG_RegisterHitMarkerKill( void ) {
    cg_hhaHitMarkerTime = cg.time;
    cg_hhaHitMarkerWasKill = 1;
}

void CG_DrawHitMarker( void ) {
    float alpha;
    int   elapsed;
    float color[4];
    char  buf[8];
    float cx, cy;

    if ( !cg.snap ) return;
    trap_Cvar_VariableStringBuffer("cg_handheldHitMarker", buf, sizeof(buf));
    if ( atof(buf) == 0.0f ) return;
    if ( cg_hhaHitMarkerTime <= 0 ) return;
    if ( cg.snap->ps.stats[STAT_HEALTH] <= 0 ) return;
    if ( cg.renderingThirdPerson ) return;

    elapsed = cg.time - cg_hhaHitMarkerTime;
    if ( elapsed < 0 || elapsed > 180 ) {
        cg_hhaHitMarkerTime = 0;
        return;
    }
    alpha = 1.0f - ( (float)elapsed / 180.0f );
    if ( alpha < 0.0f ) alpha = 0.0f;
    if ( alpha > 1.0f ) alpha = 1.0f;

    if ( cg_hhaHitMarkerWasKill ) {
        color[0] = 1.0f;  color[1] = 0.05f; color[2] = 0.05f;
    } else {
        color[0] = 1.0f;  color[1] = 1.0f;  color[2] = 0.15f;
    }
    color[3] = alpha;

    cx = 320.0f;
    cy = 240.0f;

    trap_R_SetColor( color );
    CG_DrawPic( cx - 9.0f, cy - 9.0f, 4.0f, 4.0f, cgs.media.whiteShader );
    CG_DrawPic( cx + 5.0f, cy - 9.0f, 4.0f, 4.0f, cgs.media.whiteShader );
    CG_DrawPic( cx - 9.0f, cy + 5.0f, 4.0f, 4.0f, cgs.media.whiteShader );
    CG_DrawPic( cx + 5.0f, cy + 5.0f, 4.0f, 4.0f, cgs.media.whiteShader );
    CG_DrawPic( cx - 1.0f, cy - 1.0f, 2.0f, 2.0f, cgs.media.whiteShader );
    trap_R_SetColor( NULL );
}

void CG_DrawDamageIndicator( void ) {
    float   alpha;
    int     elapsed;
    float   color[4];
    char    buf[8];
    float   cx, cy, radius;
    float   angle;
    int     i;
    float   dotX, dotY;
    float   dotSize;

    if ( !cg.snap ) return;
    trap_Cvar_VariableStringBuffer("cg_handheldDamageIndicator", buf, sizeof(buf));
    if ( atof(buf) == 0.0f ) return;
    if ( cg.damageTime <= 0.0f ) return;
    if ( cg.snap->ps.stats[STAT_HEALTH] <= 0 ) return;

    elapsed = cg.time - (int)cg.damageTime;
    if ( elapsed < 0 ) elapsed += 1000;
    if ( elapsed < 0 || elapsed > 900 ) return;

    alpha = 1.0f - ( (float)elapsed / 900.0f );
    if ( alpha < 0.0f ) alpha = 0.0f;
    if ( alpha > 1.0f ) alpha = 1.0f;

    color[0] = 1.0f;
    color[1] = 0.15f;
    color[2] = 0.10f;
    color[3] = alpha;

    cx = 320.0f;
    cy = 240.0f;
    radius = 90.0f;

    angle = atan2f( cg.damageY, cg.damageX );

    trap_R_SetColor( color );

    for ( i = -2; i <= 2; i++ ) {
        float weight;
        float segAngle;

        segAngle = angle + (float)i * 0.20f;

        dotX = cx + cosf( segAngle ) * radius;
        dotY = cy - sinf( segAngle ) * radius;

        weight = 1.0f - fabsf( (float)i ) * 0.20f;
        dotSize = 10.0f * weight * alpha;
        if ( dotSize < 3.0f ) dotSize = 3.0f;

        CG_DrawPic( dotX - dotSize * 0.5f, dotY - dotSize * 0.5f,
                    dotSize, dotSize, cgs.media.whiteShader );
    }

    if ( alpha > 0.3f ) {
        CG_DrawPic( cx - 2.0f, cy - 2.0f, 4.0f, 4.0f, cgs.media.whiteShader );
    }

    trap_R_SetColor( NULL );
}

void CG_HandheldDrawOverlays( void ) {
    CG_DrawHitMarker();
    CG_DrawDamageIndicator();
}
/* ============================================================ */
'''

    inc_pat = re.compile(r'(#include\s+"cg_local\.h"\s*\n)')
    if not inc_pat.search(content):
        print("[WARN] cg_local.h include nicht gefunden")
        return False
    content = inc_pat.sub(lambda m: m.group(1) + hitmarker_code,
                          content, count=1)

    draw2d_pat = re.compile(r'(\n[ \t]*CG_Draw2D\s*\(\s*stereoView\s*\)\s*;)')
    if draw2d_pat.search(content):
        content = draw2d_pat.sub(
            r'\1\n\n\t/* HHA_HITMARKER_V3 */\n\tCG_HandheldDrawOverlays();',
            content, count=1)
        print("[PATCHED] Hitmarker + Damage-Indicator v14.3")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_cg_event_hit():
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_event.c" in files:
            target_file = os.path.join(root, "cg_event.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_event.c not found")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "CG_RegisterHitMarkerKill" in content:
        print("[SKIP] Hit event hook already present")
        return True

    decls = "\nvoid CG_RegisterHitMarker( void );\nvoid CG_RegisterHitMarkerKill( void );\n\n"
    inc_pat = re.compile(r'(#include\s+"cg_local\.h"\s*\n)')
    if inc_pat.search(content):
        content = inc_pat.sub(lambda m: m.group(1) + decls, content, count=1)

    bullet_case = re.compile(
        r'(case\s+EV_BULLET_HIT_FLESH\s*:\s*\n'
        r'\s*DEBUGNAME\s*\(\s*"EV_BULLET_HIT_FLESH"\s*\)\s*;)')
    if bullet_case.search(content):
        content = bullet_case.sub(
            r'\1\n'
            r'\t\tif ( es->otherEntityNum == cg.snap->ps.clientNum ) {\n'
            r'\t\t\tCG_RegisterHitMarker();\n'
            r'\t\t}',
            content, count=1)
        print("[PATCHED] Hitmarker event hook on EV_BULLET_HIT_FLESH")

    death_pat = re.compile(
        r'(case\s+EV_OBITUARY\s*:\s*\n'
        r'\s*DEBUGNAME\s*\(\s*"EV_OBITUARY"\s*\)\s*;)')
    if death_pat.search(content):
        content = death_pat.sub(
            r'\1\n'
            r'\t\t/* HHA: Kill-Hitmarker (rot) */\n'
            r'\t\tif ( cg.snap && cg.snap->ps.clientNum >= 0 &&\n'
            r'\t\t     es->otherEntityNum == cg.snap->ps.clientNum ) {\n'
            r'\t\t\tCG_RegisterHitMarkerKill();\n'
            r'\t\t}',
            content, count=1)
        print("[PATCHED] Kill-Hitmarker event hook on EV_OBITUARY")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_cg_crosshair_player():
    """v14.2: Crosshair wird ROT auf Gegner."""
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_draw.c" in files:
            target_file = os.path.join(root, "cg_draw.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_draw.c not found (crosshair patch)")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "HHA_CROSSHAIR_V2" in content:
        print("[SKIP] Crosshair v14.2 bereits gepatcht")
        return True

    sig_old = re.compile(
        r'static void CG_ScanForCrosshairEntity\(\s*qboolean\s*\*changeCrosshair,\s*'
        r'qboolean\s*\*isPlayer\s*\)\s*\{')
    if not sig_old.search(content):
        print("[WARN] CG_ScanForCrosshairEntity Signatur nicht gefunden")
        return False
    content = sig_old.sub(
        'static void CG_ScanForCrosshairEntity( qboolean *changeCrosshair, '
        'qboolean *isPlayer, qboolean *isEnemyTarget ) { /* HHA_CROSSHAIR_V2 */',
        content, count=1)

    if '*isEnemyTarget = qfalse;' not in content:
        content = content.replace(
            '*isPlayer = qfalse;',
            '*isPlayer = qfalse;\n\t*isEnemyTarget = qfalse;',
            1)

    teammate_block = re.compile(
        r'(// player on same team\s*\n'
        r'\s*\*changeCrosshair = qtrue;\s*\n'
        r'\s*\})')
    if teammate_block.search(content):
        content = teammate_block.sub(
            r'\1\n\t\telse {\n'
            r'\t\t\t/* HHA_CROSSHAIR_V2: Gegner */\n'
            r'\t\t\t*isEnemyTarget = qtrue;\n'
            r'\t\t\t*changeCrosshair = qtrue;\n'
            r'\t\t}',
            content, count=1)

    sig_dc_old = re.compile(
        r'static void CG_DrawCrosshair\( qboolean changeCrosshair, qboolean isPlayer\)')
    if sig_dc_old.search(content):
        content = sig_dc_old.sub(
            'static void CG_DrawCrosshair( qboolean changeCrosshair, '
            'qboolean isPlayer, qboolean isEnemyTarget )',
            content, count=1)

    color_block = re.compile(
        r'\}\s*else if\(\s*changeCrosshair\s*\)\s*\{\s*\n'
        r'\s*if\(\s*isEnemyTarget\s*\)\s*\{\s*\n'
        r'\s*trap_R_SetColor\(\s*colorActivate\s*\)\s*;')
    if color_block.search(content):
        content = color_block.sub(
            '} else if( changeCrosshair ) {\n'
            '\t\tif( isEnemyTarget ) {\n'
            '\t\t\ttrap_R_SetColor( colorRed );',
            content, count=1)

    if 'qboolean isEnemyTarget=qfalse;' not in content:
        content = content.replace(
            'qboolean isPlayer=qfalse;\n\tqboolean changeCrosshair=qfalse;',
            'qboolean isPlayer=qfalse;\n\tqboolean changeCrosshair=qfalse;\n\t'
            'qboolean isEnemyTarget=qfalse; /* HHA_CROSSHAIR_V2 */',
            1)

    content = content.replace(
        'CG_ScanForCrosshairEntity( &changeCrosshair, &isPlayer );',
        'CG_ScanForCrosshairEntity( &changeCrosshair, &isPlayer, &isEnemyTarget );')
    content = content.replace(
        'CG_DrawCrosshair(changeCrosshair, isPlayer);',
        'CG_DrawCrosshair(changeCrosshair, isPlayer, isEnemyTarget);')

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Crosshair v14.2 in cg_draw.c")
    return True


def patch_cg_enemy_outline():
    """v14.3: Corner-Bracket-Outline um sichtbare Gegner."""
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_draw.c" in files:
            target_file = os.path.join(root, "cg_draw.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_draw.c not found (outline)")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "HHA_ENEMY_OUTLINE" in content:
        print("[SKIP] Enemy outline bereits gepatcht")
        return True

    outline_code = r'''

/* ============================================================
 * [PATCHED v14.3] Enemy Outline (visible-only, LoS verified)
 * HHA_ENEMY_OUTLINE
 * ============================================================ */
static qboolean HHA_WorldToScreen2( const vec3_t worldPoint,
                                    float *outX, float *outY, float *outDist ) {
    vec3_t delta;
    float viewX, viewY, viewZ;
    float tanHalfFovX, tanHalfFovY;
    float fovXRad, fovYRad;
    float ndcX, ndcY;

    if ( !cg.snap ) return qfalse;

    VectorSubtract( worldPoint, cg.refdef.vieworg, delta );

    viewX = DotProduct( delta, cg.refdef.viewaxis[0] );
    viewY = DotProduct( delta, cg.refdef.viewaxis[1] );
    viewZ = DotProduct( delta, cg.refdef.viewaxis[2] );

    if ( viewX < 1.0f ) return qfalse;

    fovXRad = cg.refdef.fov_x * (M_PI / 180.0f);
    fovYRad = cg.refdef.fov_y * (M_PI / 180.0f);
    tanHalfFovX = tanf( fovXRad * 0.5f );
    tanHalfFovY = tanf( fovYRad * 0.5f );

    if ( tanHalfFovX < 0.01f ) tanHalfFovX = 0.01f;
    if ( tanHalfFovY < 0.01f ) tanHalfFovY = 0.01f;

    ndcX = (viewY / viewX) / tanHalfFovX;
    ndcY = (viewZ / viewX) / tanHalfFovY;

    *outX = (1.0f + ndcX) * 0.5f * 640.0f;
    *outY = (1.0f - ndcY) * 0.5f * 480.0f;

    if ( outDist ) *outDist = viewX;

    return qtrue;
}

void CG_HandheldDrawEnemyOutlines( void ) {
    int    i;
    vec3_t eye, target;
    float  sx, sy, dist;
    float  size, corner;
    float  color[4] = { 1.0f, 0.15f, 0.15f, 0.90f };
    char   buf[8];
    float  maxRange;
    trace_t trace;

    if ( !cg.snap ) return;
    trap_Cvar_VariableStringBuffer("cg_handheldEnemyOutline", buf, sizeof(buf));
    if ( atof(buf) == 0.0f ) return;
    trap_Cvar_VariableStringBuffer("cg_handheldEnemyOutlineRange", buf, sizeof(buf));
    maxRange = (float)atof(buf);
    if ( maxRange < 100.0f ) maxRange = 100.0f;

    if ( cg.snap->ps.stats[STAT_HEALTH] <= 0 ) return;
    if ( cg.snap->ps.persistant[PERS_TEAM] >= TEAM_SPECTATOR ) return;
    if ( cg.renderingThirdPerson ) return;

    VectorCopy( cg.refdef.vieworg, eye );

    for ( i = 0; i < cg.snap->numEntities; i++ ) {
        entityState_t *ent = &cg.snap->entities[i];
        centity_t     *cent = &cg_entities[ent->number];

        if ( ent->eType != ET_PLAYER ) continue;
        if ( ent->number == cg.snap->ps.clientNum ) continue;
        if ( ent->eFlags & EF_DEAD ) continue;

        if ( cgs.gametype >= GT_TEAM ) {
            if ( cgs.clientinfo[ent->number].team ==
                 cg.snap->ps.persistant[PERS_TEAM] )
                continue;
        }

        VectorCopy( cent->lerpOrigin, target );
        target[2] += 32.0f;

        CG_Trace( &trace, eye, NULL, NULL, target,
                  cg.snap->ps.clientNum, MASK_SHOT );
        if ( trace.fraction < 0.999f ) continue;

        if ( !HHA_WorldToScreen2( target, &sx, &sy, &dist ) ) continue;
        if ( dist > maxRange ) continue;

        if ( sx < -40.0f || sx > 680.0f || sy < -40.0f || sy > 520.0f )
            continue;

        size = 1400.0f / (dist + 200.0f);
        if ( size < 8.0f )  size = 8.0f;
        if ( size > 32.0f ) size = 32.0f;
        corner = size / 3.0f;
        if ( corner < 3.0f ) corner = 3.0f;

        trap_R_SetColor( color );

        CG_DrawPic( sx - size, sy - size, corner, 2.0f, cgs.media.whiteShader );
        CG_DrawPic( sx - size, sy - size, 2.0f, corner, cgs.media.whiteShader );

        CG_DrawPic( sx + size - corner, sy - size, corner, 2.0f, cgs.media.whiteShader );
        CG_DrawPic( sx + size - 2.0f, sy - size, 2.0f, corner, cgs.media.whiteShader );

        CG_DrawPic( sx - size, sy + size - 2.0f, corner, 2.0f, cgs.media.whiteShader );
        CG_DrawPic( sx - size, sy + size - corner, 2.0f, corner, cgs.media.whiteShader );

        CG_DrawPic( sx + size - corner, sy + size - 2.0f, corner, 2.0f, cgs.media.whiteShader );
        CG_DrawPic( sx + size - 2.0f, sy + size - corner, 2.0f, corner, cgs.media.whiteShader );

        trap_R_SetColor( NULL );
    }
}
/* ============================================================ */
'''

    inc_pat = re.compile(r'(#include\s+"cg_local\.h"\s*\n)')
    if not inc_pat.search(content):
        print("[WARN] cg_local.h include nicht gefunden (outline)")
        return False
    content = inc_pat.sub(lambda m: m.group(1) + outline_code,
                          content, count=1)

    hook_anchor = "CG_HandheldDrawOverlays();"
    if hook_anchor in content:
        content = content.replace(
            hook_anchor,
            "CG_HandheldDrawEnemyOutlines();\n\tCG_HandheldDrawOverlays();",
            1)
        print("[PATCHED] Enemy Outline Draw-Call v14.3")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_vm_pure_gate():
    print("==> Patching VM pure-gate (v13.9)")
    touched = 0

    pattern = re.compile(
        r'if\s*\(\s*(cl|sv)_connectedToPureServer\s*!=\s*0\s*\)\s*'
        r'\{[^{}]*?interpret\s*=\s*VMI_COMPILED\s*;[^{}]*?\}\s*'
        r'else\s*\{([^{}]*?interpret\s*=\s*vm_(\w+)->integer\s*;[^{}]*?)\}',
        re.DOTALL
    )

    for root, _dirs, files in os.walk("code"):
        for name in files:
            if not name.endswith(".c"):
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            orig = content

            def _rep(m):
                inner = m.group(2)
                return ('/* PURE_BYPASS v13.9: native .so auch bei pure */\n'
                        '\t{\n\t' + inner + '\n\t}')

            content, n = pattern.subn(_rep, content)
            if n > 0 and content != orig:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"[PATCHED] {path}: pure-gate -> vm_cvar ({n}x)")
                touched += 1

    if touched == 0:
        pattern2 = re.compile(
            r'if\s*\(\s*(cl|sv)_connectedToPureServer[^{]*'
            r'\{[^{}]*?interpret\s*=\s*VMI_COMPILED\s*;[^{}]*\}',
            re.DOTALL
        )
        for root, _dirs, files in os.walk("code"):
            for name in files:
                if not name.endswith(".c"):
                    continue
                path = os.path.join(root, name)
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                orig = content
                content, n = pattern2.subn(
                    '/* PURE_BYPASS v13.9 */ (void)0;', content)
                if n > 0 and content != orig:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"[PATCHED] {path}: pure-gate fallback ({n}x)")
                    touched += 1

    if touched == 0:
        print("[INFO] VM pure-gate nicht gefunden (evtl. bereits entfernt)")
    return touched > 0


def patch_vm_force_native():
    print("==> Patching VM force-native (v14.0)")
    vm_c = None
    for root, _dirs, files in os.walk("code"):
        if "vm.c" in files and "qcommon" in root:
            candidate = os.path.join(root, "vm.c")
            if os.path.exists(candidate):
                vm_c = candidate
                break
    if not vm_c:
        print("[WARN] vm.c not found")
        return False

    with open(vm_c, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "PURE_BYPASS_FORCE_NATIVE" in content:
        print("[SKIP] force-native bereits gepatcht")
        return True

    if '"vm_force_native"' not in content:
        content = content.replace(
            'Cvar_Get( "vm_ui", "2", CVAR_ARCHIVE );',
            'Cvar_Get( "vm_ui", "2", CVAR_ARCHIVE );\n'
            '\tCvar_Get( "vm_force_native", "1", CVAR_ARCHIVE ); '
            '/* PURE_BYPASS_FORCE_NATIVE */',
            1
        )

    pat = re.compile(
        r'FS_FindVM\s*\(\s*&startSearch\s*,\s*filename\s*,\s*'
        r'sizeof\s*\(\s*filename\s*\)\s*,\s*module\s*,\s*'
        r'\(\s*interpret\s*==\s*VMI_NATIVE\s*\)\s*\)'
    )
    repl = ('FS_FindVM(&startSearch, filename, sizeof(filename), module,\n'
            '\t\t\t\t     Cvar_VariableIntegerValue("vm_force_native")\n'
            '\t\t\t\t         ? 1 : (interpret == VMI_NATIVE)) '
            '/* PURE_BYPASS_FORCE_NATIVE */')
    content, n = pat.subn(repl, content, count=1)
    if n == 0:
        print("[WARN] FS_FindVM enableDll-Aufruf nicht gefunden")
        return False

    with open(vm_c, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] vm.c: enableDll=1 erzwungen (Cvar vm_force_native)")
    return True


def patch_ingame_options_menu():
    target_file = None
    for root, _dirs, files in os.walk("ui"):
        if "ingame_options.menu" in files:
            target_file = os.path.join(root, "ingame_options.menu")
            break
    if not target_file:
        print("[WARN] ingame_options.menu not found in ui/")
        return False

    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "aim_assist_menu" not in content:
        insert = '''
	itemDef {
		name aim_assist_link
		group grpOptions
		type ITEM_TYPE_BUTTON
		text "Handheld Aim Assist..."
		rect ROW2 255 192 18
		textalign ITEM_ALIGN_RIGHT
		textalignx 128
		textaligny 20
		textscale .28
		forecolor 1 .75 0 1
		visible 1
		action {
			play "sound/misc/menu3.wav"
			close ingame_options
			open aim_assist_menu
		}
	}
'''
        last_brace = content.rfind("}")
        prev_brace = content.rfind("}", 0, last_brace)
        if prev_brace < 0:
            print("[WARN] ingame_options.menu has unexpected structure")
            return False
        content = content[:prev_brace] + insert + content[prev_brace:]
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
        print("[PATCHED] Aim Assist button in ingame_options.menu")

    rel_dir = os.path.join("build", "release-linux-aarch64")
    menu_dir = os.path.join(rel_dir, "smokinguns", "ui")
    os.makedirs(menu_dir, exist_ok=True)
    out_file = os.path.join(menu_dir, "ingame_options.menu")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[COPIED] ingame_options.menu -> {out_file}")
    return True


def write_settings_options_menu(menu_dir):
    path = os.path.join(menu_dir, "settings_options.menu")
    content = """#include "ui/menudef.h"
#define ROW1 80
#define ROW2 330
#define ROW3 200
{
menuDef {
	name "options_menu"
	visible 0
	fullscreen 0
	rect 0 50 640 371
	focusColor 1 .75 0 1
	style 1
	border 1
	onEsc { close options_menu ; close setup_menu ; open main }
itemDef { name window group grpControlbutton rect 2 2 632 371 style WINDOW_STYLE_FILLED border 1 bordercolor .5 .5 .5 .5 forecolor 1 1 1 1 backcolor 0 0 0 .5 visible 1 decoration }
itemDef { name other style 1 text "Game" rect 80 35 128 20 textalign ITEM_ALIGN_CENTER textalignx 64 textaligny 20 textscale .3 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name options group grpOptions text "Crosshair:" rect 208 55 18 18 ownerdraw UI_CROSSHAIR textalign ITEM_ALIGN_RIGHT textalignx 0 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Identify Target:" cvar "cg_drawCrosshairNames" rect ROW1 75 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Auto Download:" cvar "cl_allowDownload" rect ROW1 95 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Show FPS:" cvar "cg_drawfps" rect ROW1 115 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Show Time:" cvar "cg_drawTimer" rect ROW1 135 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Taunts Off:" cvar "cg_noTaunt" rect ROW1 155 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Team Chats Only:" cvar "cg_teamChatsOnly" rect ROW1 175 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "In Game Video:" cvar "r_inGameVideo" rect ROW1 195 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Show Hit Message(Target):" cvar "cg_hitmsg" rect ROW1 215 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Show Hit Message(Myself):" cvar "cg_ownhitmsg" rect ROW1 235 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Play Own Flysound:" cvar "cg_flysound" rect ROW1 255 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name other style 1 text "Performance" rect 330 35 128 20 textalign ITEM_ALIGN_CENTER textalignx 64 textaligny 20 textscale .3 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Simple Items:" cvar "cg_simpleItems" rect ROW2 55 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Marks On Walls:" cvar "cg_marks" rect ROW2 75 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Dynamic Lights:" cvar "r_dynamiclight" rect ROW2 95 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Additional Guns:" cvar "cg_addguns" rect ROW2 115 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Detailed Gunsmoke:" cvar "cg_gunsmoke" rect ROW2 135 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_MULTI text "Particles:" cvar "cg_impactparticles" cvarFloatList { "None" 0 "Few" 1 "Normal" 2 } rect ROW2 155 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Low Quality Sky:" cvar "r_fastsky" rect ROW2 175 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Force Player Models:" cvar "cg_forceModel" rect ROW2 215 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Glowing Flares:" cvar "cg_glowflares" rect ROW2 235 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Boost FPS:" cvar "cg_boostfps" rect ROW2 255 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_BUTTON text "Handheld Aim Assist..." rect ROW2 275 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 .75 0 1 visible 1 action { play "sound/misc/menu3.wav" ; close options_menu ; open aim_assist_menu } }
itemDef { name other style 1 text "Misc" rect ROW3 285 128 20 textalign ITEM_ALIGN_CENTER textalignx 64 textaligny 20 textscale .3 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Limit FPS when minimized:" cvar "com_maxfpsMinimized" rect ROW1 305 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Mute sound when minimized:" cvar "s_muteWhenMinimized" rect ROW1 325 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Limit FPS when unfocused:" cvar "com_maxfpsUnfocused" rect ROW2 305 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Mute sound when unfocused:" cvar "s_muteWhenUnfocused" rect ROW2 325 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Allow window resizing:" cvar "r_allowResize" rect ROW3 345 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
}
}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] settings_options.menu")


def write_aim_menu(menu_dir):
    """
    v14.5: Preset-Buttons nutzen setcvar statt exec.
    Grund: die UI-VM hat keinen exec-Befehl, aber setcvar funktioniert.
    """
    aim_menu = """#include "ui/menudef.h"
{
menuDef {
	name "aim_assist_menu"
	visible 0
	fullscreen 0
	rect 0 50 640 371
	focusColor 1 .75 0 1
	style 1
	border 1
	onEsc { close aim_assist_menu ; open options_menu }
itemDef { name window group grpAimButton rect 2 2 632 371 style WINDOW_STYLE_FILLED border 1 bordercolor .5 .5 .5 .5 forecolor 1 1 1 1 backcolor 0 0 0 .5 visible 1 decoration }
itemDef { name aim_title style 1 text "Handheld Aim Assist" rect 180 5 280 20 textalign ITEM_ALIGN_CENTER textalignx 140 textaligny 16 textscale .35 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name aim_preset_hdr style 1 text "AKTIVER PRESET:" rect 40 28 200 18 textalign ITEM_ALIGN_RIGHT textalignx 200 textaligny 14 textscale .26 forecolor .8 .8 .8 1 visible 1 decoration }
itemDef { name show_0 type ITEM_TYPE_TEXT text ">>> CUSTOM <<<" rect 260 28 340 18 textalign ITEM_ALIGN_LEFT textalignx 0 textaligny 14 textscale .30 forecolor .85 .85 .85 1 cvarTest "cg_handheldAimPreset" showCvar { "0" } visible 1 }
itemDef { name show_1 type ITEM_TYPE_TEXT text ">>> ONLINE (Snap-On) <<<" rect 260 28 340 18 textalign ITEM_ALIGN_LEFT textalignx 0 textaligny 14 textscale .30 forecolor .3 1 .3 1 cvarTest "cg_handheldAimPreset" showCvar { "1" } visible 1 }
itemDef { name show_2 type ITEM_TYPE_TEXT text ">>> OFFLINE (Bots) <<<" rect 260 28 340 18 textalign ITEM_ALIGN_LEFT textalignx 0 textaligny 14 textscale .30 forecolor 1 1 .3 1 cvarTest "cg_handheldAimPreset" showCvar { "2" } visible 1 }
itemDef { name show_3 type ITEM_TYPE_TEXT text ">>> AIMBOT (MAX) <<<" rect 260 28 340 18 textalign ITEM_ALIGN_LEFT textalignx 0 textaligny 14 textscale .30 forecolor 1 .3 .3 1 cvarTest "cg_handheldAimPreset" showCvar { "3" } visible 1 }
itemDef { name aim_hint_preset style 1 text "--- PRESET WAEHLEN ---" rect 20 52 600 12 textalign ITEM_ALIGN_CENTER textalignx 300 textaligny 10 textscale .20 forecolor .7 .7 .7 1 visible 1 decoration }
itemDef { name p_1 group grpAim type ITEM_TYPE_BUTTON text "1 - ONLINE (Snap-On, unlagged)" rect 100 68 440 20 textalign ITEM_ALIGN_CENTER textalignx 220 textaligny 14 textscale .26 forecolor 1 .75 0 1 visible 1 action { play "sound/misc/menu3.wav" ; setcvar "cg_handheldAimPreset" "1" ; setcvar "cg_handheldAimAssist" "1" ; setcvar "cg_handheldAimAssistFire" "1" ; setcvar "cg_handheldAimAssistHardLock" "1" ; setcvar "cg_handheldAimAssistAngle" "89" ; setcvar "cg_handheldAimAssistStrength" "1.20" ; setcvar "cg_handheldAimAssistFriction" "0.50" ; setcvar "cg_handheldAimAssistPitch" "1.50" ; setcvar "cg_handheldAimAssistSnapAngle" "15" ; setcvar "cg_handheldAimAssistSticky" "30" ; setcvar "cg_handheldAimAssistMaxDist" "8000" ; setcvar "cg_handheldAimAssistInterpolate" "1" ; setcvar "cg_handheldAimAssistUnlaggedSync" "0" ; setcvar "cg_handheldAimAssistLead" "0" ; setcvar "cg_handheldAimAssistLOS" "0" ; setcvar "cg_handheldAimAssistZoom" "1" ; setcvar "cg_handheldAimAssistZoomNear" "80" ; setcvar "cg_handheldAimAssistZoomFar" "1200" ; setcvar "cg_handheldAimAssistZoomFov" "30" ; setcvar "cg_handheldAimAssistZoomSpeed" "25" ; close aim_assist_menu ; open aim_assist_menu }
itemDef { name p_2 group grpAim type ITEM_TYPE_BUTTON text "2 - OFFLINE (Bots, sanft)" rect 100 90 440 20 textalign ITEM_ALIGN_CENTER textalignx 220 textaligny 14 textscale .26 forecolor .3 1 .3 1 visible 1 action { play "sound/misc/menu3.wav" ; setcvar "cg_handheldAimPreset" "2" ; setcvar "cg_handheldAimAssist" "1" ; setcvar "cg_handheldAimAssistFire" "1" ; setcvar "cg_handheldAimAssistHardLock" "0" ; setcvar "cg_handheldAimAssistAngle" "28" ; setcvar "cg_handheldAimAssistStrength" "0.55" ; setcvar "cg_handheldAimAssistFriction" "0.85" ; setcvar "cg_handheldAimAssistPitch" "0.80" ; setcvar "cg_handheldAimAssistSnapAngle" "5" ; setcvar "cg_handheldAimAssistSticky" "15" ; setcvar "cg_handheldAimAssistMaxDist" "3000" ; setcvar "cg_handheldAimAssistInterpolate" "1" ; setcvar "cg_handheldAimAssistUnlaggedSync" "0" ; setcvar "cg_handheldAimAssistLead" "0" ; setcvar "cg_handheldAimAssistLOS" "1" ; setcvar "cg_handheldAimAssistZoom" "1" ; setcvar "cg_handheldAimAssistZoomNear" "100" ; setcvar "cg_handheldAimAssistZoomFar" "600" ; setcvar "cg_handheldAimAssistZoomFov" "40" ; setcvar "cg_handheldAimAssistZoomSpeed" "15" ; close aim_assist_menu ; open aim_assist_menu }
itemDef { name p_3 group grpAim type ITEM_TYPE_BUTTON text "3 - AIMBOT (MAX Snap-On)" rect 100 112 440 20 textalign ITEM_ALIGN_CENTER textalignx 220 textaligny 14 textscale .26 forecolor 1 .3 .3 1 visible 1 action { play "sound/misc/menu3.wav" ; setcvar "cg_handheldAimPreset" "3" ; setcvar "cg_handheldAimAssist" "1" ; setcvar "cg_handheldAimAssistFire" "1" ; setcvar "cg_handheldAimAssistHardLock" "1" ; setcvar "cg_handheldAimAssistAngle" "89" ; setcvar "cg_handheldAimAssistStrength" "1.20" ; setcvar "cg_handheldAimAssistFriction" "0.50" ; setcvar "cg_handheldAimAssistPitch" "1.50" ; setcvar "cg_handheldAimAssistSnapAngle" "15" ; setcvar "cg_handheldAimAssistSticky" "30" ; setcvar "cg_handheldAimAssistMaxDist" "8000" ; setcvar "cg_handheldAimAssistInterpolate" "1" ; setcvar "cg_handheldAimAssistUnlaggedSync" "0" ; setcvar "cg_handheldAimAssistLead" "0" ; setcvar "cg_handheldAimAssistLOS" "0" ; setcvar "cg_handheldAimAssistZoom" "1" ; setcvar "cg_handheldAimAssistZoomNear" "80" ; setcvar "cg_handheldAimAssistZoomFar" "1200" ; setcvar "cg_handheldAimAssistZoomFov" "30" ; setcvar "cg_handheldAimAssistZoomSpeed" "25" ; close aim_assist_menu ; open aim_assist_menu }
itemDef { name p_0 group grpAim type ITEM_TYPE_BUTTON text "0 - CUSTOM (manuell)" rect 100 134 440 20 textalign ITEM_ALIGN_CENTER textalignx 220 textaligny 14 textscale .26 forecolor .85 .85 .85 1 visible 1 action { play "sound/misc/menu3.wav" ; setcvar "cg_handheldAimPreset" "0" ; close aim_assist_menu ; open aim_assist_menu }
itemDef { name aim_hint_qol style 1 text "--- LIVE WERTE ---" rect 180 162 280 12 textalign ITEM_ALIGN_CENTER textalignx 140 textaligny 10 textscale .20 forecolor .7 .7 .7 1 visible 1 decoration }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Handheld Aim Assist:" cvar "cg_handheldAimAssist" rect 60 180 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "HardLock (Snap-On):" cvar "cg_handheldAimAssistHardLock" rect 60 202 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 .3 .3 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Fire Assist:" cvar "cg_handheldAimAssistFire" rect 60 224 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Aim Cone Angle:" cvarfloat "cg_handheldAimAssistAngle" 89 5 89 rect 60 246 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Magnetism Strength:" cvarfloat "cg_handheldAimAssistStrength" 1.20 0.05 1.20 rect 60 268 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Input Friction:" cvarfloat "cg_handheldAimAssistFriction" 0.50 0.50 1.00 rect 60 290 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Auto Weapon Switch:" cvar "cg_handheldAutoSwitch" rect 60 316 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Hit Marker:" cvar "cg_handheldHitMarker" rect 60 338 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name nav1 group grpAim type ITEM_TYPE_BUTTON text "Advanced..." rect 20 360 190 22 textalign ITEM_ALIGN_CENTER textalignx 95 textaligny 16 textscale .26 forecolor 1 .75 0 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_menu ; open aim_assist_advanced_menu } }
itemDef { name nav2 group grpAim type ITEM_TYPE_BUTTON text "Dynamic Zoom..." rect 225 360 190 22 textalign ITEM_ALIGN_CENTER textalignx 95 textaligny 16 textscale .26 forecolor 1 .75 0 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_menu ; open aim_assist_zoom_menu } }
itemDef { name nav3 group grpAim type ITEM_TYPE_BUTTON text "Zurueck" rect 430 360 190 22 textalign ITEM_ALIGN_CENTER textalignx 95 textaligny 16 textscale .26 forecolor 1 1 1 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_menu ; open options_menu } }
}
}
"""
    with open(os.path.join(menu_dir, "settings_aimassist.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_menu)
    print("[PATCHED] settings_aimassist.menu (v14.5 setcvar)")

    aim_adv = """#include "ui/menudef.h"
{
menuDef {
	name "aim_assist_advanced_menu"
	visible 0
	fullscreen 0
	rect 0 50 640 371
	focusColor 1 .75 0 1
	style 1
	border 1
	onEsc { close aim_assist_advanced_menu ; open aim_assist_menu }
itemDef { name window group grpAimButton rect 2 2 632 371 style WINDOW_STYLE_FILLED border 1 bordercolor .5 .5 .5 .5 forecolor 1 1 1 1 backcolor 0 0 0 .5 visible 1 decoration }
itemDef { name aim_title style 1 text "Aim Assist - Advanced" rect 200 6 240 20 textalign ITEM_ALIGN_CENTER textalignx 120 textaligny 18 textscale .35 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Magnetism Strength:" cvarfloat "cg_handheldAimAssistStrength" 1.20 0.05 1.20 rect 80 40 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Pitch Multiplier:" cvarfloat "cg_handheldAimAssistPitch" 1.50 0.30 1.50 rect 80 64 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Sticky Target (frames):" cvarfloat "cg_handheldAimAssistSticky" 30 0 30 rect 80 88 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Snap Angle (deg):" cvarfloat "cg_handheldAimAssistSnapAngle" 15 0 15 rect 80 112 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 .75 0 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Max Target Distance:" cvarfloat "cg_handheldAimAssistMaxDist" 8000 500 8000 rect 80 136 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Line-of-Sight Check:" cvar "cg_handheldAimAssistLOS" rect 80 162 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Interpolate Position:" cvar "cg_handheldAimAssistInterpolate" rect 80 184 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 .75 0 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Unlagged-Sync (NUR non-unlagged):" cvar "cg_handheldAimAssistUnlaggedSync" rect 80 208 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Manual Lead (ms):" cvarfloat "cg_handheldAimAssistLead" 0 0 200 rect 80 232 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_BUTTON text "Zurueck" rect 220 290 200 24 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 17 textscale .28 forecolor 1 1 1 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_advanced_menu ; open aim_assist_menu } }
}
}
"""
    with open(os.path.join(menu_dir, "settings_aimassist_advanced.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_adv)
    print("[PATCHED] settings_aimassist_advanced.menu")

    aim_zoom = """#include "ui/menudef.h"
{
menuDef {
	name "aim_assist_zoom_menu"
	visible 0
	fullscreen 0
	rect 0 50 640 371
	focusColor 1 .75 0 1
	style 1
	border 1
	onEsc { close aim_assist_zoom_menu ; open aim_assist_menu }
itemDef { name window group grpAimButton rect 2 2 632 371 style WINDOW_STYLE_FILLED border 1 bordercolor .5 .5 .5 .5 forecolor 1 1 1 1 backcolor 0 0 0 .5 visible 1 decoration }
itemDef { name aim_title style 1 text "Aim Assist - Dynamic Zoom" rect 180 8 280 20 textalign ITEM_ALIGN_CENTER textalignx 140 textaligny 18 textscale .35 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Enable Dynamic Zoom:" cvar "cg_handheldAimAssistZoom" rect 80 44 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 .75 0 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Zoom Near Distance:" cvarfloat "cg_handheldAimAssistZoomNear" 80 50 1500 rect 80 76 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Zoom Far Distance:" cvarfloat "cg_handheldAimAssistZoomFar" 1200 300 4000 rect 80 100 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Target Zoom FOV:" cvarfloat "cg_handheldAimAssistZoomFov" 30 25 85 rect 80 124 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Zoom Speed:" cvarfloat "cg_handheldAimAssistZoomSpeed" 25 1 25 rect 80 148 260 20 textalign ITEM_ALIGN_RIGHT textalignx 150 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_BUTTON text "Zurueck" rect 220 200 200 24 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 17 textscale .28 forecolor 1 1 1 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_zoom_menu ; open aim_assist_menu } }
}
}
"""
    with open(os.path.join(menu_dir, "settings_aimassist_zoom.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_zoom)
    print("[PATCHED] settings_aimassist_zoom.menu")


def write_menu_override():
    if not os.path.exists("Makefile"):
        return False
    rel_dir = os.path.join("build", "release-linux-aarch64")
    menu_dir = os.path.join(rel_dir, "smokinguns", "ui")
    os.makedirs(menu_dir, exist_ok=True)

    write_settings_options_menu(menu_dir)
    write_aim_menu(menu_dir)

    menus = """// menu defs
{	
	loadMenu { "ui/main.menu" }
	loadMenu { "ui/joinserver.menu" }
	loadMenu { "ui/skirmish.menu" }
	loadMenu { "ui/createserver.menu" }

	loadMenu { "ui/demo.menu" }
	loadMenu { "ui/connect.menu" }
	loadMenu { "ui/quitcredit.menu" }

	loadMenu { "ui/settings.menu" }
	loadMenu { "ui/settings_controls.menu" }
	loadMenu { "ui/settings_system.menu" }
	loadMenu { "ui/settings_options.menu" }
	loadMenu { "ui/settings_aimassist.menu" }
	loadMenu { "ui/settings_aimassist_advanced.menu" }
	loadMenu { "ui/settings_aimassist_zoom.menu" }
	loadMenu { "ui/settings_player.menu" }
	loadMenu { "ui/settings_default.menu" }

	loadMenu { "ui/pop_password.menu" }
	loadMenu { "ui/pop_findplayer.menu" }
	loadMenu { "ui/pop_serverinfo.menu" }
	loadMenu { "ui/pop_createfavorite.menu" }
	loadMenu { "ui/pop_specify.menu" }
	loadMenu { "ui/pop_multiplayer.menu" }
	loadMenu { "ui/pop_quit.menu" }
	loadMenu { "ui/pop_error.menu" }
	loadMenu { "ui/pop_vid_restart.menu" }
	loadMenu { "ui/pop_sound_restart.menu" }
}
"""
    with open(os.path.join(menu_dir, "menus.txt"),
              "w", encoding="utf-8") as f:
        f.write(menus)
    print("[PATCHED] menus.txt")
    return True


def patch_fs_native_vm():
    print("==> Patching FS Native VM Support (v13.6)")
    touched = False

    qcommon_h = None
    for root, _dirs, files in os.walk("code"):
        if "qcommon.h" in files:
            qcommon_h = os.path.join(root, "qcommon.h")
            break

    if qcommon_h:
        with open(qcommon_h, "r", encoding="utf-8", errors="ignore") as f:
            qh = f.read()
        if "VMI_NATIVE" not in qh:
            if re.search(r'VMI_BYTECODE\s*,', qh):
                qh = re.sub(r'(VMI_BYTECODE\s*,)',
                            r'\1\n\tVMI_NATIVE,', qh, count=1)
            with open(qcommon_h, "w", encoding="utf-8") as f:
                f.write(qh)
            print("[PATCHED] qcommon.h: VMI_NATIVE enum added")
            touched = True
        else:
            print("[SKIP] VMI_NATIVE bereits definiert")

    files_c = None
    for root, _dirs, files in os.walk("code"):
        if "files.c" in files and "qcommon" in root:
            files_c = os.path.join(root, "files.c")
            break
    if not files_c:
        print("[WARN] files.c nicht gefunden")
        return touched

    with open(files_c, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "FS_NativeFindFile" in content:
        print("[SKIP] FS_NativeFindFile bereits vorhanden")
        return touched

    helper = r'''
/* ============================================================
 * [PATCHED v13.6] Native Shared Library (.so) Support (Client)
 * ============================================================ */
#define FS_NATIVE_MAX_PATH 4096

qboolean FS_NativeFindFile( const char *basename,
                            char *outPath, int outSize ) {
    char         testPath[FS_NATIVE_MAX_PATH];
    fileHandle_t f;
    int          len;

    if ( !basename || !*basename || !outPath || outSize <= 0 ) {
        return qfalse;
    }

    Com_sprintf( testPath, sizeof( testPath ), "%s/%s.so",
                 fs_basegame ? fs_basegame->string : BASEGAME, basename );
    len = FS_FOpenFileRead( testPath, &f, qfalse );
    if ( len >= 0 ) {
        if ( f ) FS_FCloseFile( f );
        Q_strncpyz( outPath, testPath, outSize );
        Com_DPrintf( "FS_NativeFindFile: '%s' (%d Bytes)\n", testPath, len );
        return qtrue;
    }

    Com_sprintf( testPath, sizeof( testPath ), "%s/%s.dll",
                 fs_basegame ? fs_basegame->string : BASEGAME, basename );
    len = FS_FOpenFileRead( testPath, &f, qfalse );
    if ( len >= 0 ) {
        if ( f ) FS_FCloseFile( f );
        Q_strncpyz( outPath, testPath, outSize );
        Com_DPrintf( "FS_NativeFindFile: '%s' (%d Bytes)\n", testPath, len );
        return qtrue;
    }

    return qfalse;
}

qboolean FS_FindVMModule( const char *basename, char *outPath,
                          int outSize, int *vmType ) {
    if ( FS_NativeFindFile( basename, outPath, outSize ) ) {
        if ( vmType ) *vmType = VMI_NATIVE;
        Com_DPrintf( "FS_FindVMModule: native '%s' bevorzugt vor QVM\n",
                     outPath );
        return qtrue;
    }
    return qfalse;
}

void FS_NativePakChecksumString( const char *basename,
                                 char *out, int outSize ) {
    if ( !basename || !*basename || !out || outSize <= 0 ) {
        if ( out && outSize > 0 ) out[0] = '\0';
        return;
    }
    Com_sprintf( out, outSize, "%s/%s.so",
                 fs_basegame ? fs_basegame->string : BASEGAME, basename );
}
/* ============================================================ */
'''

    content = content + "\n" + helper + "\n"
    with open(files_c, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] {files_c}: Client Native-VM-Funktionen")
    touched = True
    return touched


def main():
    is_smokinguns = os.path.exists("Makefile")
    is_sdl12_compat = os.path.exists(os.path.join("src", "SDL12_compat.c"))
    if not is_smokinguns and not is_sdl12_compat:
        print("[ERROR] Not in SmokinGuns or sdl12-compat source tree.")
        sys.exit(1)
    applied = 0
    if is_smokinguns:
        print("==> Patching SmokinGuns (v14.5)")
        diagnostic_dump()
        if patch_makefile(): applied += 1
        patch_q_platform()
        patch_client_cvar()
        patch_ui_cvar()
        patch_aim_assist()
        patch_cg_view()
        patch_cg_hitmarker()
        patch_cg_enemy_outline()
        patch_cg_event_hit()
        patch_cg_crosshair_player()
        patch_cl_main_namerotator()
        patch_cl_console_chatprefill()
        patch_fs_native_vm()
        patch_vm_pure_gate()
        patch_vm_force_native()
        write_menu_override()
        patch_ingame_options_menu()
    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints(): applied += 1
    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()