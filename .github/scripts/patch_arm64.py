#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

v13.2 - Performance + AimBot + In-Game-Menue:
  ALLE v13.1-Funktionen sind weiterhin enthalten (nichts entfernt).
  - NEU: Config-Cache (HHA_ReadConfig 1x pro Frame statt 3x)
  - NEU: LOS-Budget von 4 auf 1 gesenkt (CM_BoxTrace ist teuer)
  - NEU: Cvar_Set fuer Ziel-Distanz nur bei tatsaechlicher Aenderung
  - NEU: cg_handheldAimAssistHardLock (echter AimBot, instant Snap)
  - NEU: Cone-Cap auf 89 Grad wenn HardLock aktiv
  - NEU: preset_aimbot.cfg (maximale Effektivitaet)
  - FIX: ingame_options.menu wird ins Release-Verzeichnis kopiert
  - FIX: Respawn-Reset mit 4 unabhaengigen Triggern
"""

import os
import re
import sys


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


AIM_CVAR_SUFFIXES = [
    "AimAssist", "AimAssistFire", "AimAssistAngle",
    "AimAssistStrength", "AimAssistFriction", "AimAssistPitch",
    "AimAssistLead", "AimAssistSticky", "AimAssistMaxDist",
    "AimAssistLOS", "AimAssistUnlaggedSync", "AimAssistInterpolate",
    "AimAssistSnapAngle", "AimAssistZoom", "AimAssistZoomNear",
    "AimAssistZoomFar", "AimAssistZoomFov", "AimAssistZoomSpeed",
    "AimAssistHardLock",
    "AutoSwitch", "HitMarker", "DamageIndicator",
    "AimPreset",
]


def patch_client_cvar():
    path = os.path.join("code", "client", "cl_main.c")
    if not os.path.exists(path):
        print("[WARN] cl_main.c not found")
        return False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if 'cg_handheldAimAssistHardLock' in content:
        print("[SKIP] Client cvars already registered")
        return True
    anchor = 'j_up_axis =      Cvar_Get ("j_up_axis",      "2", CVAR_ARCHIVE);'
    if anchor not in content:
        print("[WARN] cl_main.c anchor not found")
        return False

    lines = [
        "\t/* [PATCHED v13.2] Handheld Aim Assist cvars */",
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
    ]
    insertion = anchor + "\n" + "\n".join(lines)
    content = content.replace(anchor, insertion, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] cl_main.c: 24 cvars registered")
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
            )
            content = content.replace(anchor, anchor + entries, 1)
            print("[PATCHED] ui_main.c: 23 cvarTable entries")

    with open(ui_main_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_aim_assist():
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
 * [PATCHED v13.2] Handheld Aim Assist
 *
 * Performance-Optimierungen (gegenueber v13.1):
 *   - Config wird 1x pro Frame gecached (HHA_RefreshConfig)
 *     statt 3x HHA_ReadConfig pro Frame
 *   - LOS-Budget auf 1 pro Frame reduziert (CM_BoxTrace teuer)
 *   - Cvar_Set fuer Ziel-Distanz nur bei tatsaechlicher Aenderung
 *
 * Neue Features:
 *   - cg_handheldAimAssistHardLock: instant Snap auf Ziel (AimBot)
 *   - Cone-Cap 89 Grad wenn HardLock aktiv
 *   - Respawn-Reset mit 4 unabhaengigen Triggern
 *
 * Alle v13.1-Funktionen (Cache, Sticky, LOS-Cache, Unlagged-Sync,
 * Interpolate, Lead, Snap, Falloff, Friction, Zoom) bleiben erhalten.
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

/* --- Zustand --- */
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
static vec3_t   hha_lastOrigin = { 0, 0, 0 };
static qboolean hha_firstCall = qtrue;

/* --- Config-Cache (Performance v13.2) --- */
static hha_config_t hha_cachedConfig;
static qboolean     hha_configValid = qfalse;
static float        hha_lastTargetDist = -1.0f;

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

    if ( clc.state != CA_ACTIVE ) {
        HHA_SetTargetDist( 0.0f );
        return -1;
    }
    if ( cl.snap.numEntities <= 0 ) {
        HHA_SetTargetDist( 0.0f );
        return -1;
    }

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

    /* Sortierung nach Winkel (Selection-Sort, O(n^2) aber n<=32) */
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

        /* HardLock ignoriert LOS-Check (AimBot schiesst durch Waende) */
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

static void HHA_UpdateCachedTarget( const hha_config_t *cfg ) {
    hha_cachedTarget = HHA_FindTarget( cfg, hha_cachedDir, &hha_cachedAngle );
    hha_cachedValid  = qtrue;
    if ( hha_cachedTarget >= 0 ) {
        hha_lastTargetNum = hha_cachedTarget;
        hha_lastTargetAge = 0;
    } else if ( ++hha_lastTargetAge > cfg->stickyFrames ) {
        hha_lastTargetNum = -1;
    }
}

/* ============================================================
 * Wird 1x pro Frame aus CL_CreateCmd aufgerufen.
 * Refresht Config-Cache und prueft Respawn (4 Trigger).
 * ============================================================ */
static void CL_HandheldUpdateTarget( void ) {
    int   curSpawn, curHealth, curPmType;
    vec3_t curOrigin;
    float  originDeltaSq;

    hha_losChecksThisFrame = 0;
    HHA_RefreshConfig();

    curSpawn  = cl.snap.ps.persistant[PERS_SPAWN_COUNT];
    curHealth = cl.snap.ps.stats[STAT_HEALTH];
    curPmType = cl.snap.ps.pm_type;

    curOrigin[0] = cl.snap.ps.origin[0];
    curOrigin[1] = cl.snap.ps.origin[1];
    curOrigin[2] = cl.snap.ps.origin[2];

    originDeltaSq =
        (curOrigin[0]-hha_lastOrigin[0]) * (curOrigin[0]-hha_lastOrigin[0]) +
        (curOrigin[1]-hha_lastOrigin[1]) * (curOrigin[1]-hha_lastOrigin[1]) +
        (curOrigin[2]-hha_lastOrigin[2]) * (curOrigin[2]-hha_lastOrigin[2]);

    /* FIX v13.2: VIER unabhaengige Reset-Trigger.
     * PERS_SPAWN_COUNT allein reicht nicht zuverlaessig. */
    if ( hha_firstCall ||
         curSpawn != hha_lastSpawnCount ||
         ( curHealth > 0 && hha_lastHealth <= 0 ) ||
         ( curPmType != PM_DEAD && hha_lastPmType == PM_DEAD ) ||
         originDeltaSq > 1000.0f * 1000.0f ) {
        int i;
        hha_firstCall      = qfalse;
        hha_lastSpawnCount = curSpawn;
        hha_lastHealth     = curHealth;
        hha_lastPmType     = curPmType;
        hha_lastOrigin[0]  = curOrigin[0];
        hha_lastOrigin[1]  = curOrigin[1];
        hha_lastOrigin[2]  = curOrigin[2];
        hha_cachedValid    = qfalse;
        hha_cachedTarget   = -1;
        hha_lastTargetNum  = -1;
        hha_lastTargetAge  = 0;
        for ( i = 0; i < HHA_LOS_CACHE_SIZE; i++ ) {
            hha_los_cache[i].valid = qfalse;
        }
    }
    hha_lastHealth = curHealth;
    hha_lastPmType = curPmType;
    hha_lastOrigin[0] = curOrigin[0];
    hha_lastOrigin[1] = curOrigin[1];
    hha_lastOrigin[2] = curOrigin[2];

    if ( !hha_cachedConfig.enabled ) {
        hha_cachedValid  = qfalse;
        hha_cachedTarget = -1;
        return;
    }
    HHA_UpdateCachedTarget( &hha_cachedConfig );
}

static void CL_HandheldInputCurve( void ) {
    hha_config_t *cfg = &hha_cachedConfig;
    int   *mx_raw, *my_raw;
    float  mag, friction = 1.0f;

    if ( !hha_configValid ) {
        HHA_ReadConfig( cfg );
        hha_configValid = qtrue;
    }
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
    qboolean firing;
    qboolean inSnap;

    if ( !hha_configValid ) {
        HHA_ReadConfig( cfg );
        hha_configValid = qtrue;
    }
    if ( !cfg->enabled ) return;
    if ( clc.state != CA_ACTIVE ) return;
    if ( !hha_cachedValid || hha_cachedTarget < 0 ) return;

    AngleVectors( cl.viewangles, forward, NULL, NULL );
    dot = DotProduct( forward, hha_cachedDir );
    if ( dot >  1.0f ) dot =  1.0f;
    if ( dot < -1.0f ) dot = -1.0f;
    currentAngle = acosf( dot ) * ( 180.0f / HHA_PI );

    /* Hard-Lock AimBot: instant Snap auf Ziel (max Effektivitaet) */
    if ( cfg->hardLock ) {
        vectoangles( hha_cachedDir, targetAngles );
        cl.viewangles[YAW]   = targetAngles[YAW];
        cl.viewangles[PITCH] = targetAngles[PITCH];
        return;
    }

    if ( currentAngle > cfg->angle ) return;

    firing = ( cmd && ( cmd->buttons & BUTTON_ATTACK ) && cfg->fireEnabled );
    if ( firing ) { magYaw = cfg->fireYaw; magPitch = cfg->firePitch; }
    else           { magYaw = cfg->strengthYaw; magPitch = cfg->strengthPitch; }

    inSnap = ( currentAngle <= cfg->snapAngle && cfg->snapAngle > 0.0f );
    if ( inSnap ) {
        magYaw   *= 2.0f;
        magPitch *= 2.0f;
    }

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
    content = joy_pat.sub(
        lambda m: m.group(1) + "\n\n\tCL_HandheldAimMagnetism( &cmd );",
        content, count=1)

    createcmd_pat = re.compile(
        r'(usercmd_t\s+CL_CreateCmd\s*\(\s*void\s*\)\s*\{)')
    if not createcmd_pat.search(content):
        print("[WARN] CL_CreateCmd not found")
    else:
        content = createcmd_pat.sub(
            r'\1\n\tCL_HandheldUpdateTarget();\n',
            content, count=1)
        print("[PATCHED] Cache + Respawn + Cvar-Recheck in CL_CreateCmd")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Aim assist v13.2 in {target_file}")
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
 * [PATCHED v13.2] Dynamic Zoom + Auto-Switch
 * ============================================================ */
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
    qboolean enabled;

    curSpawn = cg.predictedPlayerState.persistant[PERS_SPAWN_COUNT];
    if ( curSpawn != cg_hhaZoomLastSpawnCount ) {
        cg_hhaZoomLastSpawnCount = curSpawn;
        cg_hhaZoomCurrent  = 0.0f;
        cg_hhaZoomLastTime = cg.time;
    }

    if ( cg.zoomed ) return;
    enabled = ( trap_Cvar_VariableValue("cg_handheldAimAssistZoom") != 0.0f );
    if ( !enabled || cg.renderingThirdPerson ||
         cg.predictedPlayerState.pm_type == PM_INTERMISSION ||
         cg.snap->ps.stats[STAT_HEALTH] <= 0 ||
         cg.snap->ps.persistant[PERS_TEAM] >= TEAM_SPECTATOR ) {
        cg_hhaZoomCurrent  = 0.0f;
        cg_hhaZoomLastTime = cg.time;
        return;
    }

    dist      = CG_HandheldScanNearestTarget();
    nearDist  = trap_Cvar_VariableValue("cg_handheldAimAssistZoomNear");
    farDist   = trap_Cvar_VariableValue("cg_handheldAimAssistZoomFar");
    targetFov = trap_Cvar_VariableValue("cg_handheldAimAssistZoomFov");
    speed     = trap_Cvar_VariableValue("cg_handheldAimAssistZoomSpeed");

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
    if ( !trap_Cvar_VariableValue("cg_handheldAutoSwitch") ) return;

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
        if ( score > bestScore ) {
            bestScore = score;
            best = i;
        }
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
    if "CG_DrawHitMarker" in content:
        print("[SKIP] Hitmarker already present")
        return True

    hitmarker_code = r"""
/* ============================================================
 * [PATCHED v13.2] Hitmarker + Damage-Indicator
 * ============================================================ */
static int cg_hhaHitMarkerTime = 0;

void CG_RegisterHitMarker( void ) {
    cg_hhaHitMarkerTime = cg.time;
}

void CG_DrawHitMarker( void ) {
    float alpha;
    int   elapsed;
    float x, y, w, h;
    float color[4] = { 1.0f, 0.0f, 0.0f, 1.0f };

    if ( !cg.snap ) return;
    if ( !trap_Cvar_VariableValue("cg_handheldHitMarker") ) return;
    if ( cg_hhaHitMarkerTime <= 0 ) return;
    if ( cg.snap->ps.stats[STAT_HEALTH] <= 0 ) return;
    if ( cg.renderingThirdPerson ) return;

    elapsed = cg.time - cg_hhaHitMarkerTime;
    if ( elapsed < 0 || elapsed > 150 ) {
        cg_hhaHitMarkerTime = 0;
        return;
    }
    alpha = 1.0f - ( (float)elapsed / 150.0f );
    if ( alpha < 0.0f ) alpha = 0.0f;
    if ( alpha > 1.0f ) alpha = 1.0f;
    color[3] = alpha;

    x = 320.0f;
    y = 240.0f;
    w = 12.0f;
    h = 2.0f;
    trap_R_SetColor( color );
    CG_DrawPic( x - w, y - w, w, h, cgs.media.whiteShader );
    CG_DrawPic( x + 2, y + w - 2, w, h, cgs.media.whiteShader );
    CG_DrawPic( x + 2, y - w, w, h, cgs.media.whiteShader );
    CG_DrawPic( x - w, y + w - 2, w, h, cgs.media.whiteShader );
    trap_R_SetColor( NULL );
}

void CG_DrawDamageIndicator( void ) {
    float alpha;
    int   elapsed;
    float x;
    float color[4] = { 1.0f, 0.3f, 0.0f, 1.0f };

    if ( !cg.snap ) return;
    if ( !trap_Cvar_VariableValue("cg_handheldDamageIndicator") ) return;
    if ( cg.damageTime <= 0.0f ) return;
    if ( cg.snap->ps.stats[STAT_HEALTH] <= 0 ) return;

    elapsed = cg.time - (int)cg.damageTime;
    if ( elapsed < 0 || elapsed > 700 ) return;

    alpha = 1.0f - ( (float)elapsed / 700.0f );
    if ( alpha < 0.0f ) alpha = 0.0f;
    if ( alpha > 0.75f ) alpha = 0.75f;
    color[3] = alpha;

    x = 320.0f + cg.damageX * 280.0f;

    trap_R_SetColor( color );
    CG_DrawPic( x - 10.0f, 20.0f, 20.0f, 6.0f, cgs.media.whiteShader );
    trap_R_SetColor( NULL );
}

void CG_HandheldDrawOverlays( void ) {
    CG_DrawHitMarker();
    CG_DrawDamageIndicator();
}
/* ============================================================ */

"""

    inc_pat = re.compile(r'(#include\s+"cg_local\.h"\s*\n)')
    if inc_pat.search(content):
        content = inc_pat.sub(lambda m: m.group(1) + "\n" + hitmarker_code,
                              content, count=1)
    else:
        print("[WARN] cg_local.h include not found")
        return False

    draw2d_call_pat = re.compile(
        r'(\n[ \t]*CG_Draw2D\s*\(\s*stereoView\s*\)\s*;)')
    if draw2d_call_pat.search(content):
        content = draw2d_call_pat.sub(
            r'\1\n\n\tCG_HandheldDrawOverlays();',
            content, count=1)
        print("[PATCHED] Hitmarker hook after CG_Draw2D() in CG_DrawActive")

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
    if "CG_RegisterHitMarker" in content:
        print("[SKIP] Hit event hook already present")
        return True

    decls = ("\nvoid CG_RegisterHitMarker( void );\n\n")
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

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_cg_crosshair_player():
    """FIX v13.2: Crosshair wird orange bei Ziel auf gegnerisches Playermodel."""
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
    if "isEnemyTarget" in content:
        print("[SKIP] Crosshair enemy target already present")
        return True

    sig_old = re.compile(
        r'static void CG_ScanForCrosshairEntity\( qboolean \*changeCrosshair, '
        r'qboolean \*isPlayer \) \{')
    if not sig_old.search(content):
        print("[WARN] CG_ScanForCrosshairEntity signature not found")
        return False
    content = sig_old.sub(
        'static void CG_ScanForCrosshairEntity( qboolean *changeCrosshair, '
        'qboolean *isPlayer, qboolean *isEnemyTarget ) {',
        content, count=1)

    if '*isPlayer = qfalse;' not in content:
        print("[WARN] *isPlayer = qfalse; not found")
        return False
    content = content.replace(
        '*isPlayer = qfalse;',
        '*isPlayer = qfalse;\n\t*isEnemyTarget = qfalse;',
        1)

    teammate_block = re.compile(
        r'(// player on same team\s*\n'
        r'\s*\*changeCrosshair = qtrue;\s*\n'
        r'\s*\})')
    if not teammate_block.search(content):
        print("[WARN] teammate block in CG_ScanForCrosshairEntity not found")
        return False
    content = teammate_block.sub(
        r'\1\n\t\telse {\n'
        r'\t\t\t*isEnemyTarget = qtrue;\n'
        r'\t\t\t*changeCrosshair = qtrue;\n'
        r'\t\t}',
        content, count=1)

    sig_dc_old = re.compile(
        r'static void CG_DrawCrosshair\( qboolean changeCrosshair, qboolean isPlayer\)')
    if not sig_dc_old.search(content):
        print("[WARN] CG_DrawCrosshair signature not found")
        return False
    content = sig_dc_old.sub(
        'static void CG_DrawCrosshair( qboolean changeCrosshair, '
        'qboolean isPlayer, qboolean isEnemyTarget )',
        content, count=1)

    color_block = re.compile(
        r'\}\s*else if\(\s*changeCrosshair\s*\)\s*\{\s*\n'
        r'\s*if\(\s*isPlayer\s*\)\s*\{')
    if not color_block.search(content):
        print("[WARN] color block in CG_DrawCrosshair not found")
        return False
    content = color_block.sub(
        '} else if( changeCrosshair ) {\n'
        '\t\tif( isEnemyTarget ) {\n'
        '\t\t\ttrap_R_SetColor( colorActivate );\n'
        '\t\t} else if( isPlayer ) {',
        content, count=1)

    if 'qboolean isPlayer=qfalse;\n\tqboolean changeCrosshair=qfalse;' in content:
        content = content.replace(
            'qboolean isPlayer=qfalse;\n\tqboolean changeCrosshair=qfalse;',
            'qboolean isPlayer=qfalse;\n\tqboolean changeCrosshair=qfalse;\n\t'
            'qboolean isEnemyTarget=qfalse;')
        print("[PATCHED] isEnemyTarget variable added to CG_Draw2D")
    else:
        print("[WARN] isPlayer/changeCrosshair declaration not found")

    content = content.replace(
        'CG_ScanForCrosshairEntity( &changeCrosshair, &isPlayer );',
        'CG_ScanForCrosshairEntity( &changeCrosshair, &isPlayer, &isEnemyTarget );')

    content = content.replace(
        'CG_DrawCrosshair(changeCrosshair, isPlayer);',
        'CG_DrawCrosshair(changeCrosshair, isPlayer, isEnemyTarget);')

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Crosshair enemy target highlight in cg_draw.c")
    return True


def patch_ingame_options_menu():
    """FIX v13.2: Fuegt einen Button zum Aim-Assist-Menue in ingame_options.menu ein
    UND kopiert die gepatchte Datei ins Release-Verzeichnis, damit sie die
    Original-Version aus der pk3 ueberschreibt.

    Datei liegt im Source-Tree unter ui/ingame_options.menu.
    """
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
    else:
        print("[SKIP] ingame_options.menu already patched")

    # === v13.2: ins Release-Verzeichnis kopieren ===
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
itemDef { name options group grpOptions type ITEM_TYPE_YESNO text "Sync Every Frame:" cvar "weapon 5" rect ROW2 195 192 18 textalign ITEM_ALIGN_RIGHT textalignx 128 textaligny 20 textscale .28 forecolor 1 1 1 1 visible 1 }
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
    return True


def write_menu_override():
    if not os.path.exists("Makefile"):
        return False
    rel_dir = os.path.join("build", "release-linux-aarch64")
    menu_dir = os.path.join(rel_dir, "smokinguns", "ui")
    os.makedirs(menu_dir, exist_ok=True)

    write_settings_options_menu(menu_dir)

    # ------------------------------------------------------------
    # Hauptmenü Aim-Assist mit deutlicher Preset-Anzeige (4 Presets)
    # ------------------------------------------------------------
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
itemDef { name aim_title style 1 text "Handheld Aim Assist" rect 180 3 280 18 textalign ITEM_ALIGN_CENTER textalignx 140 textaligny 15 textscale .35 forecolor 1 .75 0 1 visible 1 decoration }

// === Aktiver Preset (gross, farbig) ===
itemDef { name aim_active_label style 1 text "AKTIVER PRESET:" rect 60 24 240 12 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 10 textscale .24 forecolor .7 .7 .7 1 visible 1 decoration }
itemDef { name aim_active_custom  style 1 text ">>> CUSTOM <<<"                     rect 60 38 240 18 textalign ITEM_ALIGN_CENTER textalignx 120 textaligny 14 textscale .36 forecolor 1 1 1 1     visible 1 showCvar { "cg_handheldAimPreset" "0" } }
itemDef { name aim_active_online  style 1 text ">>> ONLINE (UNLAGGED) <<<"          rect 60 38 240 18 textalign ITEM_ALIGN_CENTER textalignx 120 textaligny 14 textscale .36 forecolor .3 1 .3 1   visible 1 showCvar { "cg_handheldAimPreset" "1" } }
itemDef { name aim_active_offline style 1 text ">>> OFFLINE (BOTS) <<<"             rect 60 38 240 18 textalign ITEM_ALIGN_CENTER textalignx 120 textaligny 14 textscale .36 forecolor .3 1 .3 1   visible 1 showCvar { "cg_handheldAimPreset" "2" } }
itemDef { name aim_active_aimbot  style 1 text ">>> AIMBOT (MAX EFFEKTIVITAET) <<<" rect 60 38 240 18 textalign ITEM_ALIGN_CENTER textalignx 120 textaligny 14 textscale .34 forecolor 1 .3 .3 1   visible 1 showCvar { "cg_handheldAimPreset" "3" } }

itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO    text "Handheld Aim Assist:"  cvar "cg_handheldAimAssist"        rect 60 60 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO    text "Fire Assist:"          cvar "cg_handheldAimAssistFire"    rect 60 80 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER   text "Aim Cone Angle:"       cvarfloat "cg_handheldAimAssistAngle"    22   5   45   rect 60 103 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER   text "Magnetism Strength:"   cvarfloat "cg_handheldAimAssistStrength" 0.55 0.05 1.20 rect 60 126 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER   text "Input Friction:"       cvarfloat "cg_handheldAimAssistFriction" 0.92 0.50 1.00 rect 60 149 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }

// === Preset-Auswahl ===
itemDef { name aim_hint_preset style 1 text "--- PRESET WAEHLEN ---" rect 180 174 280 12 textalign ITEM_ALIGN_CENTER textalignx 140 textaligny 10 textscale .24 forecolor .7 .7 .7 1 visible 1 decoration }

itemDef { name p_online_inactive group grpAim type ITEM_TYPE_BUTTON text "Preset: ONLINE (Unlagged)" rect 100 190 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor 1 .75 0 1 visible 1 hideCvar { "cg_handheldAimPreset" "1" } action { play "sound/misc/menu3.wav" ; exec "preset_online.cfg" } }
itemDef { name p_online_active   group grpAim type ITEM_TYPE_BUTTON text "* ONLINE (Unlagged) *"    rect 100 190 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor .3 1 .3 1 visible 1 showCvar { "cg_handheldAimPreset" "1" } action { play "sound/misc/menu3.wav" ; exec "preset_online.cfg" } }

itemDef { name p_offline_inactive group grpAim type ITEM_TYPE_BUTTON text "Preset: OFFLINE (Bots)" rect 100 214 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor 1 .75 0 1 visible 1 hideCvar { "cg_handheldAimPreset" "2" } action { play "sound/misc/menu3.wav" ; exec "preset_offline.cfg" } }
itemDef { name p_offline_active   group grpAim type ITEM_TYPE_BUTTON text "* OFFLINE (Bots) *"     rect 100 214 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor .3 1 .3 1 visible 1 showCvar { "cg_handheldAimPreset" "2" } action { play "sound/misc/menu3.wav" ; exec "preset_offline.cfg" } }

itemDef { name p_aimbot_inactive group grpAim type ITEM_TYPE_BUTTON text "Preset: AIMBOT (MAX)"      rect 100 238 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor 1 .3 .3 1 visible 1 hideCvar { "cg_handheldAimPreset" "3" } action { play "sound/misc/menu3.wav" ; exec "preset_aimbot.cfg" } }
itemDef { name p_aimbot_active   group grpAim type ITEM_TYPE_BUTTON text "*** AIMBOT (MAX) ***"      rect 100 238 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .28 forecolor 1 .1 .1 1 visible 1 showCvar { "cg_handheldAimPreset" "3" } action { play "sound/misc/menu3.wav" ; exec "preset_aimbot.cfg" } }

itemDef { name aim_hint_qol style 1 text "--- QUALITY OF LIFE ---" rect 180 266 280 12 textalign ITEM_ALIGN_CENTER textalignx 140 textaligny 10 textscale .22 forecolor .7 .7 .7 1 visible 1 decoration }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Auto Weapon Switch:" cvar "cg_handheldAutoSwitch"      rect 60 282 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Hit Marker:"         cvar "cg_handheldHitMarker"       rect 60 302 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Damage Direction:"   cvar "cg_handheldDamageIndicator" rect 60 322 240 18 textalign ITEM_ALIGN_RIGHT textalignx 160 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 }

itemDef { name aim_options group grpAim type ITEM_TYPE_BUTTON text "Advanced Options..." rect 100 346 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor 1 .75 0 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_menu ; open aim_assist_advanced_menu } }
itemDef { name aim_options group grpAim type ITEM_TYPE_BUTTON text "Dynamic Zoom..."      rect 320 346 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor 1 .75 0 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_menu ; open aim_assist_zoom_menu } }
itemDef { name aim_options group grpAim type ITEM_TYPE_BUTTON text "Zurueck"              rect 210 372 200 20 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 14 textscale .26 forecolor 1 1 1 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_menu ; open options_menu } }
}
}
"""
    with open(os.path.join(menu_dir, "settings_aimassist.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_menu)
    print("[PATCHED] Menu: settings_aimassist.menu")

    # ------------------------------------------------------------
    # Advanced-Menue
    # ------------------------------------------------------------
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
itemDef { name aim_title style 1 text "Aim Assist - Advanced" rect 200 10 240 20 textalign ITEM_ALIGN_CENTER textalignx 120 textaligny 18 textscale .35 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "HardLock AimBot (Instant Snap):" cvar "cg_handheldAimAssistHardLock" rect 80 40 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 15 textscale .28 forecolor 1 .3 .3 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Interpolate Position:" cvar "cg_handheldAimAssistInterpolate" rect 80 65 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 15 textscale .28 forecolor 1 .75 0 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Unlagged-Sync (NUR non-unlagged):" cvar "cg_handheldAimAssistUnlaggedSync" rect 80 90 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Manual Lead (ms):" cvarfloat "cg_handheldAimAssistLead" 0 0 200 rect 80 115 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Pitch Strength Multiplier:" cvarfloat "cg_handheldAimAssistPitch" 0.80 0.30 1.50 rect 80 140 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Sticky Target (frames):" cvarfloat "cg_handheldAimAssistSticky" 15 0 30 rect 80 165 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Snap Angle (degrees):" cvarfloat "cg_handheldAimAssistSnapAngle" 5 0 15 rect 80 190 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 .75 0 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Max Target Distance:" cvarfloat "cg_handheldAimAssistMaxDist" 3000 500 8000 rect 80 215 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Line-of-Sight Check:" cvar "cg_handheldAimAssistLOS" rect 80 240 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 15 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssist" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_BUTTON text "Back" rect 220 275 200 24 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 17 textscale .28 forecolor 1 1 1 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_advanced_menu ; open aim_assist_menu } }
}
}
"""
    with open(os.path.join(menu_dir, "settings_aimassist_advanced.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_adv)
    print("[PATCHED] Menu: settings_aimassist_advanced.menu")

    # ------------------------------------------------------------
    # Zoom-Menue
    # ------------------------------------------------------------
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
itemDef { name aim_title style 1 text "Aim Assist - Dynamic Zoom" rect 180 10 280 20 textalign ITEM_ALIGN_CENTER textalignx 140 textaligny 18 textscale .35 forecolor 1 .75 0 1 visible 1 decoration }
itemDef { name aim_options group grpAim type ITEM_TYPE_YESNO text "Enable Dynamic Zoom:" cvar "cg_handheldAimAssistZoom" rect 80 50 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 15 textscale .28 forecolor 1 .75 0 1 visible 1 }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Zoom Near Distance:" cvarfloat "cg_handheldAimAssistZoomNear" 100 50 1500 rect 80 80 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssistZoom" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Zoom Far Distance:" cvarfloat "cg_handheldAimAssistZoomFar" 800 300 4000 rect 80 105 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssistZoom" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Target Zoom FOV:" cvarfloat "cg_handheldAimAssistZoomFov" 45 25 85 rect 80 130 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssistZoom" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_SLIDER text "Zoom Speed:" cvarfloat "cg_handheldAimAssistZoomSpeed" 12 1 25 rect 80 155 220 20 textalign ITEM_ALIGN_RIGHT textalignx 140 textaligny 12 textscale .28 forecolor 1 1 1 1 visible 1 cvarTest "cg_handheldAimAssistZoom" disableCvar { "0" } }
itemDef { name aim_options group grpAim type ITEM_TYPE_BUTTON text "Back" rect 220 210 200 24 textalign ITEM_ALIGN_CENTER textalignx 100 textaligny 17 textscale .28 forecolor 1 1 1 1 visible 1 action { play "sound/misc/menu3.wav" ; close aim_assist_zoom_menu ; open aim_assist_menu } }
}
}
"""
    with open(os.path.join(menu_dir, "settings_aimassist_zoom.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_zoom)
    print("[PATCHED] Menu: settings_aimassist_zoom.menu")

    # ------------------------------------------------------------
    # Preset: Online
    # ------------------------------------------------------------
    preset_online = """// Preset: Online (Unlagged Server)
seta cg_handheldAimPreset "1"
seta cg_handheldAimAssist "1"
seta cg_handheldAimAssistFire "1"
seta cg_handheldAimAssistAngle "22"
seta cg_handheldAimAssistStrength "0.55"
seta cg_handheldAimAssistFriction "0.92"
seta cg_handheldAimAssistPitch "0.80"
seta cg_handheldAimAssistSnapAngle "5"
seta cg_handheldAimAssistSticky "15"
seta cg_handheldAimAssistMaxDist "3000"
seta cg_handheldAimAssistInterpolate "1"
seta cg_handheldAimAssistUnlaggedSync "0"
seta cg_handheldAimAssistLead "0"
seta cg_handheldAimAssistLOS "1"
seta cg_handheldAimAssistHardLock "0"
seta cg_handheldAimAssistZoom "1"
seta cg_handheldAimAssistZoomNear "100"
seta cg_handheldAimAssistZoomFar "800"
seta cg_handheldAimAssistZoomFov "45"
seta cg_handheldAimAssistZoomSpeed "12"
echo "^2[Preset] ^7ONLINE (Unlagged) geladen"
"""
    with open(os.path.join(menu_dir, "preset_online.cfg"),
              "w", encoding="utf-8") as f:
        f.write(preset_online)
    print("[PATCHED] Preset: preset_online.cfg")

    # ------------------------------------------------------------
    # Preset: Offline
    # ------------------------------------------------------------
    preset_offline = """// Preset: Offline (Bots)
seta cg_handheldAimPreset "2"
seta cg_handheldAimAssist "1"
seta cg_handheldAimAssistFire "1"
seta cg_handheldAimAssistAngle "28"
seta cg_handheldAimAssistStrength "0.55"
seta cg_handheldAimAssistFriction "0.85"
seta cg_handheldAimAssistPitch "0.80"
seta cg_handheldAimAssistSnapAngle "5"
seta cg_handheldAimAssistSticky "15"
seta cg_handheldAimAssistMaxDist "3000"
seta cg_handheldAimAssistInterpolate "0"
seta cg_handheldAimAssistUnlaggedSync "0"
seta cg_handheldAimAssistLead "0"
seta cg_handheldAimAssistLOS "1"
seta cg_handheldAimAssistHardLock "0"
seta cg_handheldAimAssistZoom "1"
seta cg_handheldAimAssistZoomNear "100"
seta cg_handheldAimAssistZoomFar "600"
seta cg_handheldAimAssistZoomFov "40"
seta cg_handheldAimAssistZoomSpeed "15"
echo "^2[Preset] ^7OFFLINE (Bots) geladen"
"""
    with open(os.path.join(menu_dir, "preset_offline.cfg"),
              "w", encoding="utf-8") as f:
        f.write(preset_offline)
    print("[PATCHED] Preset: preset_offline.cfg")

    # ------------------------------------------------------------
    # Preset: Aimbot (max Effektivitaet, HardLock aktiv)
    # ------------------------------------------------------------
    preset_aimbot = """// Preset: Aimbot (Maximum Effectiveness, HardLock aktiv)
// WARNUNG: Sehr aggressiv. Auf oeffentlichen Servern oft verboten.
// HardLock = instant Snap auf Ziel ohne Smoothing.
seta cg_handheldAimPreset "3"
seta cg_handheldAimAssist "1"
seta cg_handheldAimAssistFire "1"
seta cg_handheldAimAssistAngle "89"
seta cg_handheldAimAssistStrength "1.20"
seta cg_handheldAimAssistFriction "0.50"
seta cg_handheldAimAssistPitch "1.50"
seta cg_handheldAimAssistSnapAngle "15"
seta cg_handheldAimAssistSticky "30"
seta cg_handheldAimAssistMaxDist "8000"
seta cg_handheldAimAssistInterpolate "1"
seta cg_handheldAimAssistUnlaggedSync "1"
seta cg_handheldAimAssistLead "0"
seta cg_handheldAimAssistLOS "0"
seta cg_handheldAimAssistHardLock "1"
seta cg_handheldAimAssistZoom "1"
seta cg_handheldAimAssistZoomNear "50"
seta cg_handheldAimAssistZoomFar "1500"
seta cg_handheldAimAssistZoomFov "30"
seta cg_handheldAimAssistZoomSpeed "25"
echo "^1[Preset] ^7AIMBOT (MAX) geladen ^1- VORSICHT ONLINE!"
"""
    with open(os.path.join(menu_dir, "preset_aimbot.cfg"),
              "w", encoding="utf-8") as f:
        f.write(preset_aimbot)
    print("[PATCHED] Preset: preset_aimbot.cfg")

    # ------------------------------------------------------------
    # menus.txt
    # ------------------------------------------------------------
    menus = """// menu defs
// 
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
    print("[PATCHED] Menu: menus.txt")

    return True


def main():
    is_smokinguns = os.path.exists("Makefile")
    is_sdl12_compat = os.path.exists(os.path.join("src", "SDL12_compat.c"))
    if not is_smokinguns and not is_sdl12_compat:
        print("[ERROR] Not in SmokinGuns or sdl12-compat source tree.")
        sys.exit(1)
    applied = 0
    if is_smokinguns:
        print("==> Patching SmokinGuns (v13.2)")
        diagnostic_dump()
        if patch_makefile(): applied += 1
        patch_q_platform()
        patch_client_cvar()
        patch_ui_cvar()
        patch_aim_assist()
        patch_cg_view()
        patch_cg_hitmarker()
        patch_cg_event_hit()
        patch_cg_crosshair_player()
        write_menu_override()
        patch_ingame_options_menu()
    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints(): applied += 1
    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()