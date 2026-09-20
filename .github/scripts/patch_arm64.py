#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

v11.4 - Finale Version:
  - settings_options.menu wird KOMPLETT geschrieben (mit Aim-Assist-Button)
    Grund: Die Datei existiert nur im Pak, nicht im Source-Tree. In-Place-
    Patching schlug immer fehl.
  - Alle anderen Funktionen aus v11.3 unveraendert.
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


# ============================================================================
# Makefile / Platform / SDL12-compat
# ============================================================================
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


# ============================================================================
# CVAR-REGISTRIERUNG
# ============================================================================
AIM_CVAR_SUFFIXES = [
    "AimAssist", "AimAssistFire", "AimAssistAngle",
    "AimAssistStrength", "AimAssistFriction", "AimAssistPitch",
    "AimAssistLead", "AimAssistSticky", "AimAssistMaxDist",
    "AimAssistLOS", "AimAssistUnlaggedSync", "AimAssistInterpolate",
    "AimAssistSnapAngle", "AimAssistZoom", "AimAssistZoomNear",
    "AimAssistZoomFar", "AimAssistZoomFov", "AimAssistZoomSpeed",
    "AutoSwitch", "HitMarker", "DamageIndicator",
]


def patch_client_cvar():
    path = os.path.join("code", "client", "cl_main.c")
    if not os.path.exists(path):
        print("[WARN] cl_main.c not found")
        return False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if 'cg_handheldAutoSwitch' in content:
        print("[SKIP] Client cvars already registered")
        return True
    anchor = 'j_up_axis =      Cvar_Get ("j_up_axis",      "2", CVAR_ARCHIVE);'
    if anchor not in content:
        print("[WARN] cl_main.c anchor not found")
        return False

    lines = [
        "\t/* [PATCHED] Handheld Aim Assist cvars - basic */",
        "\tCvar_Get (\"cg_handheldAimAssist\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistFire\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistAngle\", \"18\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistStrength\", \"0.35\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistFriction\", \"0.85\", CVAR_ARCHIVE);",
        "\t/* [PATCHED] Handheld Aim Assist cvars - advanced */",
        "\tCvar_Get (\"cg_handheldAimAssistPitch\", \"0.75\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistLead\", \"0\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistSticky\", \"15\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistMaxDist\", \"4096\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistLOS\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistUnlaggedSync\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistInterpolate\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistSnapAngle\", \"3\", CVAR_ARCHIVE);",
        "\t/* [PATCHED] Handheld Aim Assist cvars - dynamic zoom */",
        "\tCvar_Get (\"cg_handheldAimAssistZoom\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomNear\", \"200\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomFar\", \"2000\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomFov\", \"65\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldAimAssistZoomSpeed\", \"6\", CVAR_ARCHIVE);",
        "\t/* [PATCHED] Handheld QoL cvars */",
        "\tCvar_Get (\"cg_handheldAutoSwitch\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldHitMarker\", \"1\", CVAR_ARCHIVE);",
        "\tCvar_Get (\"cg_handheldDamageIndicator\", \"1\", CVAR_ARCHIVE);",
        "\t/* [PATCHED] Internal - Client -> Cgame Bruecke */",
        "\tCvar_Get (\"cg_handheldAimAssistTargetDist\", \"0\", 0);",
    ]
    insertion = anchor + "\n" + "\n".join(lines)
    content = content.replace(anchor, insertion, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] cl_main.c: 21 cvars + 1 internal bridge cvar registered")
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
                print(f"[PATCHED] ui_local.h: {len(AIM_CVAR_SUFFIXES)} extern decls added")

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
            print(f"[PATCHED] ui_main.c: {len(AIM_CVAR_SUFFIXES)} vmCvar_t decls added")

    if '"cg_handheldAutoSwitch"' not in content:
        anchor = '\t{ &ui_brassTime, "cg_brassTime", "2500", CVAR_ARCHIVE },'
        if anchor in content:
            entries = (
                '\n\t{ &ui_handheldAimAssist, "cg_handheldAimAssist", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistFire, "cg_handheldAimAssistFire", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistAngle, "cg_handheldAimAssistAngle", "18", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistStrength, "cg_handheldAimAssistStrength", "0.35", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistFriction, "cg_handheldAimAssistFriction", "0.85", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistPitch, "cg_handheldAimAssistPitch", "0.75", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistLead, "cg_handheldAimAssistLead", "0", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistSticky, "cg_handheldAimAssistSticky", "15", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistMaxDist, "cg_handheldAimAssistMaxDist", "4096", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistLOS, "cg_handheldAimAssistLOS", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistUnlaggedSync, "cg_handheldAimAssistUnlaggedSync", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistInterpolate, "cg_handheldAimAssistInterpolate", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistSnapAngle, "cg_handheldAimAssistSnapAngle", "3", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoom, "cg_handheldAimAssistZoom", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomNear, "cg_handheldAimAssistZoomNear", "200", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomFar, "cg_handheldAimAssistZoomFar", "2000", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomFov, "cg_handheldAimAssistZoomFov", "65", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAimAssistZoomSpeed, "cg_handheldAimAssistZoomSpeed", "6", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldAutoSwitch, "cg_handheldAutoSwitch", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldHitMarker, "cg_handheldHitMarker", "1", CVAR_ARCHIVE },'
                '\n\t{ &ui_handheldDamageIndicator, "cg_handheldDamageIndicator", "1", CVAR_ARCHIVE },'
            )
            content = content.replace(anchor, anchor + entries, 1)
            print("[PATCHED] ui_main.c: 21 cvarTable entries added")

    with open(ui_main_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


# ============================================================================
# AIM-ASSIST (cl_input.c)
# ============================================================================
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
 * [PATCHED v11.4] Handheld Aim Assist (Input-Kurve + Magnetismus)
 * Hinweis: PVS-Check entfernt, da CM_PointLeafnum/CM_LeafArea in SG
 * nicht oeffentlich verfuegbar sind. LOS via CM_BoxTrace() direkt.
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
#define HHA_LOS_POS_EPSILON   4.0f

typedef struct {
    qboolean enabled;
    qboolean fireEnabled;
    qboolean losEnabled;
    qboolean unlaggedSync;
    qboolean interpolate;
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
    vec3_t   entPos;
    vec3_t   eyePos;
    qboolean los;
    qboolean valid;
} hha_los_cache_entry_t;

static hha_los_cache_entry_t hha_los_cache[HHA_LOS_CACHE_SIZE];
static int      hha_lastTargetNum = -1;
static int      hha_lastTargetAge = 0;
static int      hha_cachedTarget = -1;
static float    hha_cachedAngle  = 999.0f;
static vec3_t   hha_cachedDir    = { 0, 0, 0 };
static qboolean hha_cachedValid  = qfalse;

static void HHA_ReadConfig( hha_config_t *cfg ) {
    float angle    = Cvar_VariableValue("cg_handheldAimAssistAngle");
    float strength = Cvar_VariableValue("cg_handheldAimAssistStrength");
    float friction = Cvar_VariableValue("cg_handheldAimAssistFriction");
    float pitchMul = Cvar_VariableValue("cg_handheldAimAssistPitch");
    float leadMs   = Cvar_VariableValue("cg_handheldAimAssistLead");
    float maxDist  = Cvar_VariableValue("cg_handheldAimAssistMaxDist");
    float snapAng  = Cvar_VariableValue("cg_handheldAimAssistSnapAngle");
    int   sticky   = Cvar_VariableIntegerValue("cg_handheldAimAssistSticky");

    if ( angle    <  5.0f )   angle    =  5.0f;
    if ( angle    > 30.0f )   angle    = 30.0f;
    if ( strength <  0.05f )  strength =  0.05f;
    if ( strength >  0.60f )  strength =  0.60f;
    if ( friction <  0.50f )  friction =  0.50f;
    if ( friction >  1.00f )  friction =  1.00f;
    if ( pitchMul <  0.30f )  pitchMul =  0.30f;
    if ( pitchMul >  1.50f )  pitchMul =  1.50f;
    if ( leadMs   <  0.0f )   leadMs   =  0.0f;
    if ( leadMs   > 200.0f )  leadMs   = 200.0f;
    if ( maxDist  < 500.0f )  maxDist  = 500.0f;
    if ( maxDist  > 8000.0f ) maxDist  = 8000.0f;
    if ( snapAng  <  0.0f )   snapAng  =  0.0f;
    if ( snapAng  > 10.0f )   snapAng  = 10.0f;
    if ( sticky   < 0 )       sticky   = 0;
    if ( sticky   > 30 )      sticky   = 30;

    cfg->enabled       = ( Cvar_VariableIntegerValue("cg_handheldAimAssist") != 0 );
    cfg->fireEnabled   = ( Cvar_VariableIntegerValue("cg_handheldAimAssistFire") != 0 );
    cfg->losEnabled    = ( Cvar_VariableIntegerValue("cg_handheldAimAssistLOS") != 0 );
    cfg->unlaggedSync  = ( Cvar_VariableIntegerValue("cg_handheldAimAssistUnlaggedSync") != 0 );
    cfg->interpolate   = ( Cvar_VariableIntegerValue("cg_handheldAimAssistInterpolate") != 0 );
    cfg->angle         = angle;
    cfg->falloff       = angle * 0.45f;
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

static qboolean HHA_PosEqual( const vec3_t a, const vec3_t b ) {
    return ( fabsf( a[0] - b[0] ) < HHA_LOS_POS_EPSILON &&
             fabsf( a[1] - b[1] ) < HHA_LOS_POS_EPSILON &&
             fabsf( a[2] - b[2] ) < HHA_LOS_POS_EPSILON );
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
            if ( HHA_PosEqual( hha_los_cache[i].entPos, toFeet ) &&
                 HHA_PosEqual( hha_los_cache[i].eyePos, fromFeet ) ) {
                return hha_los_cache[i].los;
            }
            freeSlot = i;
            break;
        }
        if ( freeSlot < 0 && !hha_los_cache[i].valid ) freeSlot = i;
    }

    CM_BoxTrace( &tr, eye, chest, NULL, NULL, 0, CONTENTS_SOLID, 0 );
    if ( freeSlot < 0 ) freeSlot = 0;
    hha_los_cache[freeSlot].entNum  = entNum;
    VectorCopy( toFeet,   hha_los_cache[freeSlot].entPos );
    VectorCopy( fromFeet, hha_los_cache[freeSlot].eyePos );
    hha_los_cache[freeSlot].los     = ( tr.fraction >= 0.999f );
    hha_los_cache[freeSlot].valid   = qtrue;
    return hha_los_cache[freeSlot].los;
}

static void HHA_GetPredictedPos( const entityState_t *ent, const hha_config_t *cfg, vec3_t out ) {
    float dt = 0.0f;
    if ( cfg->interpolate ) {
        float snapAgeMs = (float)( cl.serverTime - cl.snap.serverTime );
        if ( snapAgeMs < 0.0f ) snapAgeMs = 0.0f;
        if ( snapAgeMs > 200.0f ) snapAgeMs = 200.0f;
        dt = snapAgeMs * 0.001f;
    }
    if ( cfg->unlaggedSync && !cfg->interpolate ) {
        dt = (float)cl.snap.ping * 0.0005f;
        if ( dt > 0.15f ) dt = 0.15f;
    }
    if ( cfg->leadTime > 0.0f ) dt += cfg->leadTime;
    out[0] = ent->pos.trBase[0] + ent->pos.trDelta[0] * dt;
    out[1] = ent->pos.trBase[1] + ent->pos.trDelta[1] * dt;
    out[2] = ent->pos.trBase[2] + ent->pos.trDelta[2] * dt;
}

static int HHA_FindTarget( const hha_config_t *cfg, vec3_t bestDir, float *bestAngleOut ) {
    int    i, best = -1;
    float  bestAngle = cfg->angle, bestDistSq = 0.0f;
    vec3_t forward, toEnt, predFeet;

    *bestAngleOut = 999.0f;
    if ( clc.state != CA_ACTIVE ) {
        Cvar_Set( "cg_handheldAimAssistTargetDist", "0" );
        return -1;
    }
    if ( cl.snap.numEntities <= 0 ) {
        Cvar_Set( "cg_handheldAimAssistTargetDist", "0" );
        return -1;
    }
    AngleVectors( cl.viewangles, forward, NULL, NULL );

    for ( i = 0; i < cl.snap.numEntities; i++ ) {
        entityState_t *ent = &cl.parseEntities[
            ( cl.snap.parseEntitiesNum + i ) & ( MAX_PARSE_ENTITIES - 1 ) ];
        float dx, dy, dz, distSq, dot, angle;

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
        if ( ent->number == hha_lastTargetNum && angle < cfg->angle + 5.0f ) {
            angle *= 0.60f;
        }
        if ( angle < bestAngle ) {
            if ( cfg->losEnabled ) {
                if ( !HHA_HasLineOfSight( ent->number, cl.snap.ps.origin, predFeet ) ) continue;
            }
            bestAngle  = angle;
            best       = ent->number;
            bestDistSq = distSq;
            VectorCopy( toEnt, bestDir );
        }
    }
    *bestAngleOut = bestAngle;
    if ( best >= 0 ) {
        Cvar_Set( "cg_handheldAimAssistTargetDist",
                  va( "%.1f", (float)sqrt( (double)bestDistSq ) ) );
    } else {
        Cvar_Set( "cg_handheldAimAssistTargetDist", "0" );
    }
    return best;
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

static void CL_HandheldInputCurve( void ) {
    hha_config_t cfg;
    int   *mx_raw, *my_raw;
    float  mag, friction = 1.0f;

    HHA_ReadConfig( &cfg );
    if ( !cfg.enabled ) return;

    HHA_UpdateCachedTarget( &cfg );
    mx_raw = &cl.mouseDx[cl.mouseIndex];
    my_raw = &cl.mouseDy[cl.mouseIndex];
    mag = sqrtf( (float)(*mx_raw * *mx_raw) + (float)(*my_raw * *my_raw) );
    if ( hha_cachedTarget >= 0 && mag > 0.0f && mag < HHA_FRICTION_MAX_MAG ) {
        friction = cfg.friction;
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
    hha_config_t cfg;
    vec3_t forward, targetAngles;
    float  dot, currentAngle, yawDiff, pitchDiff, strength;
    float  magYaw, magPitch;
    qboolean firing;

    HHA_ReadConfig( &cfg );
    if ( !cfg.enabled ) return;
    if ( clc.state != CA_ACTIVE ) return;
    if ( !hha_cachedValid || hha_cachedTarget < 0 ) return;

    AngleVectors( cl.viewangles, forward, NULL, NULL );
    dot = DotProduct( forward, hha_cachedDir );
    if ( dot >  1.0f ) dot =  1.0f;
    if ( dot < -1.0f ) dot = -1.0f;
    currentAngle = acosf( dot ) * ( 180.0f / HHA_PI );
    if ( currentAngle > cfg.angle ) return;

    firing = ( cmd && ( cmd->buttons & BUTTON_ATTACK ) && cfg.fireEnabled );
    if ( firing ) { magYaw = cfg.fireYaw; magPitch = cfg.firePitch; }
    else           { magYaw = cfg.strengthYaw; magPitch = cfg.strengthPitch; }

    if ( currentAngle <= cfg.snapAngle && cfg.snapAngle > 0.0f ) {
        magYaw *= 2.5f; magPitch *= 2.5f;
    }
    vectoangles( hha_cachedDir, targetAngles );
    yawDiff   = targetAngles[YAW]   - cl.viewangles[YAW];
    pitchDiff = targetAngles[PITCH] - cl.viewangles[PITCH];
    while ( yawDiff   >  180.0f ) yawDiff   -= 360.0f;
    while ( yawDiff   < -180.0f ) yawDiff   += 360.0f;
    while ( pitchDiff >  180.0f ) pitchDiff -= 360.0f;
    while ( pitchDiff < -180.0f ) pitchDiff += 360.0f;

    if ( currentAngle <= cfg.falloff ) strength = 1.0f;
    else {
        strength = 1.0f - ( currentAngle - cfg.falloff ) /
                          ( cfg.angle - cfg.falloff );
        if ( strength < 0.0f ) strength = 0.0f;
    }
    cl.viewangles[YAW]   += yawDiff   * magYaw   * strength;
    cl.viewangles[PITCH] += pitchDiff * magPitch * strength;
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

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Aim assist v11.4 in {target_file}")
    return True


# ============================================================================
# cg_view.c: Dynamic Zoom + Auto-Weapon-Switcher
# ============================================================================
def patch_cg_view():
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_view.c" in files:
            target_file = os.path.join(root, "cg_view.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_view.c not found - skipping cg_view patches")
        return False

    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    zoom_helper = r"""
/* ============================================================
 * [PATCHED v11.4] Dynamic Zoom + Auto-Weapon-Switcher (cg_view.c)
 * ============================================================ */
static float cg_hhaZoomCurrent  = 0.0f;
static int   cg_hhaZoomLastTime = 0;

static void CG_HandheldApplyZoom( void ) {
    float    nearDist, farDist, targetFov, speed;
    float    dist, targetZoom, deltaTime, factor, lerpRate;
    float    baseFov, newFov, x;
    qboolean enabled;

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
    dist      = trap_Cvar_VariableValue("cg_handheldAimAssistTargetDist");
    nearDist  = trap_Cvar_VariableValue("cg_handheldAimAssistZoomNear");
    farDist   = trap_Cvar_VariableValue("cg_handheldAimAssistZoomFar");
    targetFov = trap_Cvar_VariableValue("cg_handheldAimAssistZoomFov");
    speed     = trap_Cvar_VariableValue("cg_handheldAimAssistZoomSpeed");

    if ( nearDist  <  100.0f ) nearDist  =  100.0f;
    if ( nearDist  >  800.0f ) nearDist  =  800.0f;
    if ( farDist   <  800.0f ) farDist   =  800.0f;
    if ( farDist   > 6000.0f ) farDist   = 6000.0f;
    if ( targetFov <   30.0f ) targetFov =   30.0f;
    if ( targetFov >   85.0f ) targetFov =   85.0f;
    if ( speed     <    1.0f ) speed     =    1.0f;
    if ( speed     >   20.0f ) speed     =   20.0f;
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

/* ============================================================
 * [PATCHED v11.4] Auto-Weapon-Switcher
 * Ammo: ps->ammo[weapon] = Magazin,
 *       ps->ammo[bg_weaponlist[weapon].clip] = Reserve (clip>0)
 * clip==0 fuer KNIFE/DYNAMITE/MOLOTOV/NONE.
 * Akimbo (SF_SEC_PISTOL): Extra-Slot WP_AKIMBO (15).
 * ============================================================ */
static int cg_hhaLastSwitchTime = 0;

static void CG_HandheldAutoSwitch( void ) {
    int curWeapon, i, clip;
    int curAmmo, curReserve;
    int best = -1, bestScore = -1;

    if ( !cg.snap ) return;
    if ( !trap_Cvar_VariableValue("cg_handheldAutoSwitch") ) return;
    if ( cg.snap->ps.pm_type == PM_INTERMISSION ) return;
    if ( cg.snap->ps.pm_type == PM_DEAD ) return;
    if ( cg.snap->ps.stats[STAT_HEALTH] <= 0 ) return;
    if ( cg.snap->ps.persistant[PERS_TEAM] >= TEAM_SPECTATOR ) return;
    if ( cg.time - cg_hhaLastSwitchTime < 500 ) return;

    curWeapon = cg.snap->ps.weapon;
    if ( curWeapon <= WP_NONE || curWeapon >= WP_NUM_WEAPONS ) return;
    if ( curWeapon == WP_KNIFE ) return;
    if ( curWeapon == WP_GATLING ) return;
    if ( ( curWeapon == WP_DYNAMITE || curWeapon == WP_MOLOTOV ) &&
         cg.snap->ps.ammo[curWeapon] > 0 ) return;

    curAmmo = cg.snap->ps.ammo[curWeapon];
    if ( curAmmo > 0 ) return;

    if ( ( cg.snap->ps.stats[STAT_FLAGS] & SF_SEC_PISTOL ) &&
         bg_weaponlist[curWeapon].wp_sort == WPS_PISTOL ) {
        if ( cg.snap->ps.ammo[WP_AKIMBO] > 0 ) return;
    }

    clip = bg_weaponlist[curWeapon].clip;
    curReserve = 0;
    if ( clip > 0 && clip < WP_SEC_PISTOL ) {
        curReserve = cg.snap->ps.ammo[clip];
    }
    if ( curReserve > 0 ) return;

    for ( i = 1; i < WP_NUM_WEAPONS; i++ ) {
        int a, c, score;
        if ( i == curWeapon ) continue;
        if ( i == WP_KNIFE ) continue;
        if ( i == WP_GATLING ) continue;
        if ( i == WP_DYNAMITE || i == WP_MOLOTOV ) continue;
        if ( !(cg.snap->ps.stats[STAT_WEAPONS] & (1 << i)) ) continue;

        a = cg.snap->ps.ammo[i];
        c = 0;
        if ( bg_weaponlist[i].clip > 0 &&
             bg_weaponlist[i].clip < WP_SEC_PISTOL ) {
            c = cg.snap->ps.ammo[bg_weaponlist[i].clip];
        }
        if ( a <= 0 && c <= 0 ) continue;

        score = a * 10 + c;
        if ( score > bestScore ) {
            bestScore = score;
            best = i;
        }
    }

    if ( best >= 0 && best != curWeapon ) {
        cg.weaponSelect       = best;
        cg.weaponSelectTime   = cg.time;
        cg_hhaLastSwitchTime  = cg.time;
    }
}
/* ============================================================ */

"""

    if "CG_HandheldApplyZoom" not in content:
        calc_anchor_pat = re.compile(r'(/\*\s*\n=+\s*\nCG_CalcFov\s*\n)')
        if not calc_anchor_pat.search(content):
            print("[WARN] CG_CalcFov comment anchor not found in cg_view.c")
            return False
        content = calc_anchor_pat.sub(lambda m: zoom_helper + m.group(1),
                                      content, count=1)

        fov_set_pat = re.compile(
            r'(cg\.refdef\.fov_x\s*=\s*fov_x\s*;\s*\n'
            r'\s*cg\.refdef\.fov_y\s*=\s*fov_y\s*;)')
        if not fov_set_pat.search(content):
            print("[WARN] FOV assignment anchor not found in CG_CalcFov")
            return False
        content = fov_set_pat.sub(
            r'\1\n\n\t/* [PATCHED v11.4] Dynamic Zoom */\n\tCG_HandheldApplyZoom();',
            content, count=1)
        print("[PATCHED] Dynamic Zoom hook inserted into CG_CalcFov")

    if "CG_HandheldAutoSwitch()" not in content or "CG_HandheldAutoSwitch( void )" not in content:
        upd_pat = re.compile(r'(CG_UpdateCvars\s*\(\s*\)\s*;)')
        if not upd_pat.search(content):
            print("[WARN] CG_UpdateCvars anchor not found")
            return False
        content = upd_pat.sub(
            r'\1\n\n\t/* [PATCHED v11.4] Auto-Weapon-Switcher */\n'
            r'\tCG_HandheldAutoSwitch();',
            content, count=1)
        print("[PATCHED] Auto-Switch hook inserted after CG_UpdateCvars()")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


# ============================================================================
# cg_draw.c: Hitmarker + Damage-Indicator
# ============================================================================
def patch_cg_hitmarker():
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_draw.c" in files:
            target_file = os.path.join(root, "cg_draw.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_draw.c not found - skipping Hitmarker")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "CG_DrawHitMarker" in content:
        print("[SKIP] Hitmarker already present")
        return True

    hitmarker_code = r"""
/* ============================================================
 * [PATCHED v11.4] Hitmarker + Damage-Richtungsanzeige
 * Nutzt cgs.media.whiteShader (kein zusaetzliches Asset).
 * Damage-Indicator nutzt cg.damageX (-1..1) und cg.damageTime
 * direkt aus CG_DamageFeedback() in cg_playerstate.c.
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
/* ============================================================ */

"""

    draw2d_pat = re.compile(r'(/\*\s*\n=+\s*\nCG_Draw2D\s*\n)')
    if not draw2d_pat.search(content):
        print("[WARN] CG_Draw2D comment anchor not found in cg_draw.c")
        return False
    content = draw2d_pat.sub(lambda m: hitmarker_code + m.group(1), content, count=1)
    print("[PATCHED] Hitmarker helper injected before CG_Draw2D comment")

    score_anchor = re.compile(
        r'(\n[ \t]*cg\.scoreBoardShowing\s*=\s*CG_DrawScoreboard\s*\(\s*\)\s*;)')
    if score_anchor.search(content):
        content = score_anchor.sub(
            r'\n\n\t/* [PATCHED v11.4] Hitmarker + Damage-Indicator */\n'
            r'\tCG_DrawHitMarker();\n'
            r'\tCG_DrawDamageIndicator();'
            r'\1', content, count=1)
        print("[PATCHED] Hitmarker/Damage-Indicator hooks before CG_DrawScoreboard()")
    else:
        print("[WARN] CG_DrawScoreboard anchor not found")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


# ============================================================================
# cg_event.c: Hitmarker-Event
# ============================================================================
def patch_cg_event_hit():
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cg_event.c" in files:
            target_file = os.path.join(root, "cg_event.c")
            break
    if not target_file or not os.path.exists(target_file):
        print("[WARN] cg_event.c not found - skipping hit event hook")
        return False
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if "CG_RegisterHitMarker" in content:
        print("[SKIP] Hit event hook already present")
        return True

    decls = ("\n/* [PATCHED v11.4] Externer Hitmarker-Helper */\n"
             "void CG_RegisterHitMarker( void );\n\n")
    inc_pat = re.compile(r'(#include\s+"cg_local\.h"\s*\n)')
    if inc_pat.search(content):
        content = inc_pat.sub(lambda m: m.group(1) + decls, content, count=1)
        print("[PATCHED] cg_event.c: extern decl added")

    bullet_case = re.compile(
        r'(case\s+EV_BULLET_HIT_FLESH\s*:\s*\n'
        r'\s*DEBUGNAME\s*\(\s*"EV_BULLET_HIT_FLESH"\s*\)\s*;)')
    if bullet_case.search(content):
        content = bullet_case.sub(
            r'\1\n\t\t/* [PATCHED v11.4] Hitmarker nur wenn wir der Shooter sind */\n'
            r'\t\tif ( es->otherEntityNum == cg.snap->ps.clientNum &&\n'
            r'\t\t     es->eventParm != cg.snap->ps.clientNum ) {\n'
            r'\t\t\tCG_RegisterHitMarker();\n'
            r'\t\t}',
            content, count=1)
        print("[PATCHED] Hitmarker event hook on EV_BULLET_HIT_FLESH")
    else:
        print("[WARN] EV_BULLET_HIT_FLESH case not found in cg_event.c")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    return True


# ============================================================================
# settings_options.menu: KOMPLETTE Datei schreiben (mit Aim-Assist-Button)
# ============================================================================
def write_settings_options_menu(menu_dir):
    """Schreibt settings_options.menu komplett mit Aim-Assist-Button.
    Der Button wird nach 'Boost FPS' (ROW2 255) eingefuegt, vor dem
    'Misc'-Header (ROW3 285). Alle Original-Items bleiben erhalten."""
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

itemDef {
	name window
	group grpControlbutton
	rect 2 2 632 371
	style WINDOW_STYLE_FILLED
	border 1
	bordercolor .5 .5 .5 .5
	forecolor 1 1 1 1
	backcolor 0 0 0 .5
	visible 1
	decoration
}

itemDef {
	name other
	style 1
	text "Game"
	rect 80 35 128 20
	textalign ITEM_ALIGN_CENTER
	textalignx 64
	textaligny 20
	textscale .3
	forecolor 1 .75 0 1
	visible 1
	decoration
}

itemDef {
	name options
	group grpOptions
	text "Crosshair:"
	rect 208 55 18 18
	ownerdraw UI_CROSSHAIR
	textalign ITEM_ALIGN_RIGHT
	textalignx 0
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Identify Target:"
	cvar "cg_drawCrosshairNames"
	rect ROW1 75 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Auto Download:"
	cvar "cl_allowDownload"
	rect ROW1 95 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Show FPS:"
	cvar "cg_drawfps"
	rect ROW1 115 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Show Time:"
	cvar "cg_drawTimer"
	rect ROW1 135 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Taunts Off:"
	cvar "cg_noTaunt"
	rect ROW1 155 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Team Chats Only:"
	cvar "cg_teamChatsOnly"
	rect ROW1 175 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "In Game Video:"
	cvar "r_inGameVideo"
	rect ROW1 195 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Show Hit Message(Target):"
	cvar "cg_hitmsg"
	rect ROW1 215 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Show Hit Message(Myself):"
	cvar "cg_ownhitmsg"
	rect ROW1 235 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Play Own Flysound:"
	cvar "cg_flysound"
	rect ROW1 255 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name other
	style 1
	text "Performance"
	rect 330 35 128 20
	textalign ITEM_ALIGN_CENTER
	textalignx 64
	textaligny 20
	textscale .3
	forecolor 1 .75 0 1
	visible 1
	decoration
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Simple Items:"
	cvar "cg_simpleItems"
	rect ROW2 55 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Marks On Walls:"
	cvar "cg_marks"
	rect ROW2 75 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Dynamic Lights:"
	cvar "r_dynamiclight"
	rect ROW2 95 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Additional Guns:"
	cvar "cg_addguns"
	rect ROW2 115 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Detailed Gunsmoke:"
	cvar "cg_gunsmoke"
	rect ROW2 135 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_MULTI
	text "Particles:"
	cvar "cg_impactparticles"
	cvarFloatList { "None" 0 "Few" 1 "Normal" 2 }
	rect ROW2 155 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Low Quality Sky:"
	cvar "r_fastsky"
	rect ROW2 175 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Sync Every Frame:"
	cvar "weapon 5"
	rect ROW2 195 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Force Player Models:"
	cvar "cg_forceModel"
	rect ROW2 215 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Glowing Flares:"
	cvar "cg_glowflares"
	rect ROW2 235 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Boost FPS:"
	cvar "cg_boostfps"
	rect ROW2 255 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_BUTTON
	text "Handheld Aim Assist..."
	rect ROW2 275 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 .75 0 1
	visible 1
	action { play "sound/misc/menu3.wav" ;
		close options_menu ;
		open aim_assist_menu }
}

itemDef {
	name other
	style 1
	text "Misc"
	rect ROW3 285 128 20
	textalign ITEM_ALIGN_CENTER
	textalignx 64
	textaligny 20
	textscale .3
	forecolor 1 .75 0 1
	visible 1
	decoration
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Limit FPS when minimized:"
	cvar "com_maxfpsMinimized"
	rect ROW1 305 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Mute sound when minimized:"
	cvar "s_muteWhenMinimized"
	rect ROW1 325 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Limit FPS when unfocused:"
	cvar "com_maxfpsUnfocused"
	rect ROW2 305 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Mute sound when unfocused:"
	cvar "s_muteWhenUnfocused"
	rect ROW2 325 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name options
	group grpOptions
	type ITEM_TYPE_YESNO
	text "Allow window resizing:"
	cvar "r_allowResize"
	rect ROW3 345 192 18
	textalign ITEM_ALIGN_RIGHT
	textalignx 128
	textaligny 20
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

}
}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] settings_options.menu: complete file with 'Handheld Aim Assist...' button")
    return True


# ============================================================================
# MENU-DATEIEN (Aim-Assist-Menues)
# ============================================================================
def write_menu_override():
    if not os.path.exists("Makefile"):
        return False
    rel_dir = os.path.join("build", "release-linux-aarch64")
    menu_dir = os.path.join(rel_dir, "smokinguns", "ui")
    os.makedirs(menu_dir, exist_ok=True)

    # ---------- settings_options.menu KOMPLETT schreiben ----------
    write_settings_options_menu(menu_dir)

    # ---------- settings_aimassist.menu ----------
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

itemDef {
	name window
	group grpAimButton
	rect 2 2 632 371
	style WINDOW_STYLE_FILLED
	border 1
	bordercolor .5 .5 .5 .5
	forecolor 1 1 1 1
	backcolor 0 0 0 .5
	visible 1
	decoration
}

itemDef {
	name aim_title
	style 1
	text "Handheld Aim Assist"
	rect 180 8 280 18
	textalign ITEM_ALIGN_CENTER
	textalignx 140
	textaligny 15
	textscale .35
	forecolor 1 .75 0 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Handheld Aim Assist:"
	cvar "cg_handheldAimAssist"
	rect 60 40 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 15
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Fire Assist:"
	cvar "cg_handheldAimAssistFire"
	rect 60 62 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 15
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Aim Cone Angle:"
	cvarfloat "cg_handheldAimAssistAngle" 18 5 30
	rect 60 88 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Magnetism Strength:"
	cvarfloat "cg_handheldAimAssistStrength" 0.35 0.05 0.60
	rect 60 113 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Input Friction:"
	cvarfloat "cg_handheldAimAssistFriction" 0.85 0.50 1.00
	rect 60 138 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_hint_qol
	style 1
	text "--- Quality of Life ---"
	rect 180 165 280 14
	textalign ITEM_ALIGN_CENTER
	textalignx 140
	textaligny 11
	textscale .22
	forecolor .7 .7 .7 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Auto Weapon Switch:"
	cvar "cg_handheldAutoSwitch"
	rect 60 185 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 15
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Hit Marker:"
	cvar "cg_handheldHitMarker"
	rect 60 207 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 15
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Damage Direction:"
	cvar "cg_handheldDamageIndicator"
	rect 60 229 240 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 160
	textaligny 15
	textscale .28
	forecolor 1 1 1 1
	visible 1
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_BUTTON
	text "Advanced Options..."
	rect 220 256 200 22
	textalign ITEM_ALIGN_CENTER
	textalignx 100
	textaligny 16
	textscale .28
	forecolor 1 .75 0 1
	visible 1
	action { play "sound/misc/menu3.wav" ;
		close aim_assist_menu ;
		open aim_assist_advanced_menu }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_BUTTON
	text "Dynamic Zoom..."
	rect 220 282 200 22
	textalign ITEM_ALIGN_CENTER
	textalignx 100
	textaligny 16
	textscale .28
	forecolor 1 .75 0 1
	visible 1
	action { play "sound/misc/menu3.wav" ;
		close aim_assist_menu ;
		open aim_assist_zoom_menu }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_BUTTON
	text "Back"
	rect 220 308 200 22
	textalign ITEM_ALIGN_CENTER
	textalignx 100
	textaligny 16
	textscale .28
	forecolor 1 1 1 1
	visible 1
	action { play "sound/misc/menu3.wav" ;
		close aim_assist_menu ;
		open options_menu }
}

}
}
"""

    with open(os.path.join(menu_dir, "settings_aimassist.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_menu)
    print("[PATCHED] Menu: settings_aimassist.menu")

    # ---------- settings_aimassist_advanced.menu ----------
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

itemDef {
	name window
	group grpAimButton
	rect 2 2 632 371
	style WINDOW_STYLE_FILLED
	border 1
	bordercolor .5 .5 .5 .5
	forecolor 1 1 1 1
	backcolor 0 0 0 .5
	visible 1
	decoration
}

itemDef {
	name aim_title
	style 1
	text "Aim Assist - Advanced"
	rect 200 10 240 20
	textalign ITEM_ALIGN_CENTER
	textalignx 120
	textaligny 18
	textscale .35
	forecolor 1 .75 0 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Interpolate Position:"
	cvar "cg_handheldAimAssistInterpolate"
	rect 80 40 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 15
	textscale .28
	forecolor 1 .75 0 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Unlagged-Sync:"
	cvar "cg_handheldAimAssistUnlaggedSync"
	rect 80 65 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 15
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Manual Lead (ms):"
	cvarfloat "cg_handheldAimAssistLead" 0 0 200
	rect 80 90 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Pitch Strength:"
	cvarfloat "cg_handheldAimAssistPitch" 0.75 0.30 1.50
	rect 80 115 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Sticky Target:"
	cvarfloat "cg_handheldAimAssistSticky" 15 0 30
	rect 80 140 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Snap Angle:"
	cvarfloat "cg_handheldAimAssistSnapAngle" 3 0 10
	rect 80 165 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 .75 0 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Max Target Distance:"
	cvarfloat "cg_handheldAimAssistMaxDist" 4096 500 8000
	rect 80 190 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Line-of-Sight Check:"
	cvar "cg_handheldAimAssistLOS"
	rect 80 215 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 15
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssist"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_BUTTON
	text "Back"
	rect 220 260 200 24
	textalign ITEM_ALIGN_CENTER
	textalignx 100
	textaligny 17
	textscale .28
	forecolor 1 1 1 1
	visible 1
	action { play "sound/misc/menu3.wav" ;
		close aim_assist_advanced_menu ;
		open aim_assist_menu }
}

}
}
"""

    with open(os.path.join(menu_dir, "settings_aimassist_advanced.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_adv)
    print("[PATCHED] Menu: settings_aimassist_advanced.menu")

    # ---------- settings_aimassist_zoom.menu ----------
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

itemDef {
	name window
	group grpAimButton
	rect 2 2 632 371
	style WINDOW_STYLE_FILLED
	border 1
	bordercolor .5 .5 .5 .5
	forecolor 1 1 1 1
	backcolor 0 0 0 .5
	visible 1
	decoration
}

itemDef {
	name aim_title
	style 1
	text "Aim Assist - Dynamic Zoom"
	rect 180 10 280 20
	textalign ITEM_ALIGN_CENTER
	textalignx 140
	textaligny 18
	textscale .35
	forecolor 1 .75 0 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Enable Dynamic Zoom:"
	cvar "cg_handheldAimAssistZoom"
	rect 80 50 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 15
	textscale .28
	forecolor 1 .75 0 1
	visible 1
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Zoom Near Distance:"
	cvarfloat "cg_handheldAimAssistZoomNear" 200 100 800
	rect 80 80 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssistZoom"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Zoom Far Distance:"
	cvarfloat "cg_handheldAimAssistZoomFar" 2000 800 6000
	rect 80 105 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssistZoom"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Target Zoom FOV:"
	cvarfloat "cg_handheldAimAssistZoomFov" 65 30 85
	rect 80 130 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssistZoom"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_SLIDER
	text "Zoom Speed:"
	cvarfloat "cg_handheldAimAssistZoomSpeed" 6 1 20
	rect 80 155 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
	textaligny 12
	textscale .28
	forecolor 1 1 1 1
	visible 1
	cvarTest "cg_handheldAimAssistZoom"
	disableCvar { "0" }
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_BUTTON
	text "Back"
	rect 220 210 200 24
	textalign ITEM_ALIGN_CENTER
	textalignx 100
	textaligny 17
	textscale .28
	forecolor 1 1 1 1
	visible 1
	action { play "sound/misc/menu3.wav" ;
		close aim_assist_zoom_menu ;
		open aim_assist_menu }
}

}
}
"""

    with open(os.path.join(menu_dir, "settings_aimassist_zoom.menu"),
              "w", encoding="utf-8") as f:
        f.write(aim_zoom)
    print("[PATCHED] Menu: settings_aimassist_zoom.menu")

    # ---------- menus.txt ----------
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


# ============================================================================
# MAIN
# ============================================================================
def main():
    is_smokinguns = os.path.exists("Makefile")
    is_sdl12_compat = os.path.exists(os.path.join("src", "SDL12_compat.c"))
    if not is_smokinguns and not is_sdl12_compat:
        print("[ERROR] Not in SmokinGuns or sdl12-compat source tree.")
        sys.exit(1)
    applied = 0
    if is_smokinguns:
        print("==> Patching SmokinGuns (v11.4)")
        diagnostic_dump()
        if patch_makefile(): applied += 1
        patch_q_platform()
        patch_client_cvar()
        patch_ui_cvar()
        patch_aim_assist()
        patch_cg_view()
        patch_cg_hitmarker()
        patch_cg_event_hit()
        write_menu_override()
    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints(): applied += 1
    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()