#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

[EXTENDED] Handheld aim assist v8:
  - Client-seitige Snapshot-Interpolation fuer praezise Online-Treffer
  - Aggressivere Standardwerte (Magnetismus, Pitch, Friction)
  - PVS-Vorfilter + LOS-Cache (behebt Lag in Feuergefechten)
  - Snap-to-Target bei sehr nahem Ziel
  - Vollstaendige Menue-Integration (Basic + Advanced)
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


def patch_client_cvar():
    path = os.path.join("code", "client", "cl_main.c")
    if not os.path.exists(path):
        print("[WARN] cl_main.c not found")
        return False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if 'cg_handheldAimAssistInterpolate' in content:
        print(f"[SKIP] Client cvars already registered")
        return True
    anchor = 'j_up_axis =      Cvar_Get ("j_up_axis",      "2", CVAR_ARCHIVE);'
    if anchor not in content:
        print("[WARN] cl_main.c anchor not found")
        return False
    insertion = anchor + "\n" + (
        "\t/* [PATCHED] Handheld Aim Assist cvars - basic */\n"
        "\tCvar_Get (\"cg_handheldAimAssist\", \"1\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistFire\", \"1\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistAngle\", \"18\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistStrength\", \"0.35\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistFriction\", \"0.85\", CVAR_ARCHIVE);\n"
        "\t/* [PATCHED] Handheld Aim Assist cvars - advanced */\n"
        "\tCvar_Get (\"cg_handheldAimAssistPitch\", \"0.75\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistLead\", \"0\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistSticky\", \"15\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistMaxDist\", \"4096\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistLOS\", \"1\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistUnlaggedSync\", \"1\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistInterpolate\", \"1\", CVAR_ARCHIVE);\n"
        "\tCvar_Get (\"cg_handheldAimAssistSnapAngle\", \"3\", CVAR_ARCHIVE);"
    )
    content = content.replace(anchor, insertion, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] cl_main.c: 13 cvars registered")
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
        if "ui_handheldAimAssistInterpolate" not in content:
            anchor = "extern vmCvar_t\tui_brassTime;"
            if anchor in content:
                decls = (
                    "extern vmCvar_t\tui_handheldAimAssist;\n"
                    "extern vmCvar_t\tui_handheldAimAssistFire;\n"
                    "extern vmCvar_t\tui_handheldAimAssistAngle;\n"
                    "extern vmCvar_t\tui_handheldAimAssistStrength;\n"
                    "extern vmCvar_t\tui_handheldAimAssistFriction;\n"
                    "extern vmCvar_t\tui_handheldAimAssistPitch;\n"
                    "extern vmCvar_t\tui_handheldAimAssistLead;\n"
                    "extern vmCvar_t\tui_handheldAimAssistSticky;\n"
                    "extern vmCvar_t\tui_handheldAimAssistMaxDist;\n"
                    "extern vmCvar_t\tui_handheldAimAssistLOS;\n"
                    "extern vmCvar_t\tui_handheldAimAssistUnlaggedSync;\n"
                    "extern vmCvar_t\tui_handheldAimAssistInterpolate;\n"
                    "extern vmCvar_t\tui_handheldAimAssistSnapAngle;\n"
                )
                content = content.replace(anchor, decls + anchor, 1)
                with open(ui_local_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print("[PATCHED] ui_local.h: 13 extern decls added")

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
    if "ui_handheldAimAssistInterpolate;" not in content:
        anchor = "vmCvar_t\tui_brassTime;"
        if anchor in content:
            decls = (
                "vmCvar_t\tui_handheldAimAssist;\n"
                "vmCvar_t\tui_handheldAimAssistFire;\n"
                "vmCvar_t\tui_handheldAimAssistAngle;\n"
                "vmCvar_t\tui_handheldAimAssistStrength;\n"
                "vmCvar_t\tui_handheldAimAssistFriction;\n"
                "vmCvar_t\tui_handheldAimAssistPitch;\n"
                "vmCvar_t\tui_handheldAimAssistLead;\n"
                "vmCvar_t\tui_handheldAimAssistSticky;\n"
                "vmCvar_t\tui_handheldAimAssistMaxDist;\n"
                "vmCvar_t\tui_handheldAimAssistLOS;\n"
                "vmCvar_t\tui_handheldAimAssistUnlaggedSync;\n"
                "vmCvar_t\tui_handheldAimAssistInterpolate;\n"
                "vmCvar_t\tui_handheldAimAssistSnapAngle;\n"
            )
            content = content.replace(anchor, decls + anchor, 1)
    if '"cg_handheldAimAssistInterpolate"' not in content:
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
            )
            content = content.replace(anchor, anchor + entries, 1)
    with open(ui_main_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] ui_main.c: 13 cvars registered")
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
        print(f"[SKIP] Aim assist already present")
        return True

    helper_code = r"""
/* ============================================================
 * [PATCHED] Handheld Aim Assist v8
 * ============================================================
 *  Verbesserungen gegenueber v7:
 *    - Client-seitige Snapshot-Interpolation fuer Online
 *    - Aggressivere Magnetismus- und Pitch-Werte
 *    - Snap-to-Target bei sehr nahem Ziel
 *    - PVS-Vorfilter + LOS-Cache (Lag-Fix)
 *    - 13 CVARs fuer Feinabstimmung
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
#define HHA_AIM_THRESHOLD     0.5f
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

static int hha_lastTargetNum = -1;
static int hha_lastTargetAge = 0;

static int      hha_cachedTarget   = -1;
static float    hha_cachedAngle    = 999.0f;
static vec3_t   hha_cachedDir      = { 0, 0, 0 };
static qboolean hha_cachedValid    = qfalse;

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

static qboolean HHA_IsInPVS( const vec3_t pos ) {
    int leaf    = CM_PointLeafnum( pos );
    int area    = CM_LeafArea( leaf );
    if ( area < 0 ) return qfalse;
    return ( ( cl.snap.areamask[area >> 3] & ( 1 << ( area & 7 ) ) ) != 0 );
}

static qboolean HHA_HasLineOfSight( int entNum, const vec3_t fromFeet, const vec3_t toFeet ) {
    trace_t tr;
    vec3_t  eye, chest;
    int     i, freeSlot = -1;

    if ( !HHA_IsInPVS( toFeet ) ) {
        return qfalse;
    }

    eye[0] = fromFeet[0];
    eye[1] = fromFeet[1];
    eye[2] = fromFeet[2] + cl.snap.ps.viewheight;

    chest[0] = toFeet[0];
    chest[1] = toFeet[1];
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
        if ( freeSlot < 0 && !hha_los_cache[i].valid ) {
            freeSlot = i;
        }
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

/* Extrapoliert die Position des Gegners basierend auf trDelta und der
 * Zeit seit dem letzten Snapshot. Kompensiert die Client-Interpolation. */
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

    if ( cfg->leadTime > 0.0f ) {
        dt += cfg->leadTime;
    }

    out[0] = ent->pos.trBase[0] + ent->pos.trDelta[0] * dt;
    out[1] = ent->pos.trBase[1] + ent->pos.trDelta[1] * dt;
    out[2] = ent->pos.trBase[2] + ent->pos.trDelta[2] * dt;
}

static int HHA_FindTarget( const hha_config_t *cfg, vec3_t bestDir, float *bestAngleOut ) {
    int    i, best = -1;
    float  bestAngle = cfg->angle;
    vec3_t forward, toEnt, predFeet;

    *bestAngleOut = 999.0f;
    if ( clc.state != CA_ACTIVE ) return -1;
    if ( cl.snap.numEntities <= 0 ) return -1;

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
                if ( !HHA_HasLineOfSight( ent->number, cl.snap.ps.origin, predFeet ) ) {
                    continue;
                }
            }
            bestAngle = angle;
            best      = ent->number;
            VectorCopy( toEnt, bestDir );
        }
    }

    *bestAngleOut = bestAngle;
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
    int   *mx_raw;
    int   *my_raw;
    float  mag;
    float  friction = 1.0f;

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
    if ( firing ) {
        magYaw   = cfg.fireYaw;
        magPitch = cfg.firePitch;
    } else {
        magYaw   = cfg.strengthYaw;
        magPitch = cfg.strengthPitch;
    }

    /* Snap-to-Target: wenn sehr nah am Ziel, stark erhoehte Korrektur */
    if ( currentAngle <= cfg.snapAngle && cfg.snapAngle > 0.0f ) {
        magYaw   *= 2.5f;
        magPitch *= 2.5f;
    }

    vectoangles( hha_cachedDir, targetAngles );
    yawDiff   = targetAngles[YAW]   - cl.viewangles[YAW];
    pitchDiff = targetAngles[PITCH] - cl.viewangles[PITCH];

    while ( yawDiff   >  180.0f ) yawDiff   -= 360.0f;
    while ( yawDiff   < -180.0f ) yawDiff   += 360.0f;
    while ( pitchDiff >  180.0f ) pitchDiff -= 360.0f;
    while ( pitchDiff < -180.0f ) pitchDiff += 360.0f;

    if ( currentAngle <= cfg.falloff ) {
        strength = 1.0f;
    } else {
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
    print(f"[PATCHED] Aim assist v8 in {target_file}")
    return True


def write_menu_override():
    if not os.path.exists("Makefile"):
        return False
    rel_dir = os.path.join("build", "release-linux-aarch64")
    menu_dir = os.path.join(rel_dir, "smokinguns", "ui")
    os.makedirs(menu_dir, exist_ok=True)

    # ----------------------------------------------------------------
    # 1. settings_options.menu
    # ----------------------------------------------------------------
    settings_options = """#include "ui/menudef.h"
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
	forecolor 1 1 1 1
	visible 1
	action { play "sound/misc/menu3.wav" ;
		close options_menu ;
		open aim_assist_menu }
}

itemDef {
	name other
	style 1
	text "Misc"
	rect ROW3 305 128 20
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
	text "Mute sound when minimized:"
	cvar "s_muteWhenMinimized"
	rect ROW1 345 192 18
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
	text "Mute sound when unfocused:"
	cvar "s_muteWhenUnfocused"
	rect ROW2 345 192 18
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
	rect ROW3 365 192 18
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

    with open(os.path.join(menu_dir, "settings_options.menu"),
              "w", encoding="utf-8") as f:
        f.write(settings_options)
    print("[PATCHED] Menu: settings_options.menu")

    # ----------------------------------------------------------------
    # 2. settings_aimassist.menu
    # ----------------------------------------------------------------
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
	name aim_subtitle
	style 1
	text "Disable for online play to avoid suspicious demo footage."
	rect 100 32 440 18
	textalign ITEM_ALIGN_CENTER
	textalignx 220
	textaligny 14
	textscale .22
	forecolor .8 .8 .8 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Handheld Aim Assist:"
	cvar "cg_handheldAimAssist"
	rect 80 60 220 20
	textalign ITEM_ALIGN_RIGHT
	textalignx 140
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
	rect 80 85 220 20
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
	text "Aim Cone Angle:"
	cvarfloat "cg_handheldAimAssistAngle" 18 5 30
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
	text "Magnetism Strength:"
	cvarfloat "cg_handheldAimAssistStrength" 0.35 0.05 0.60
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
	text "Input Friction:"
	cvarfloat "cg_handheldAimAssistFriction" 0.85 0.50 1.00
	rect 80 165 220 20
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
	name aim_hint1
	style 1
	text "Advanced: Lead, Pitch, Sticky, Snap, Interpolate, LOS."
	rect 60 200 520 16
	textalign ITEM_ALIGN_CENTER
	textalignx 260
	textaligny 12
	textscale .2
	forecolor .7 .7 .7 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_BUTTON
	text "Advanced Options..."
	rect 220 225 200 24
	textalign ITEM_ALIGN_CENTER
	textalignx 100
	textaligny 17
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
	text "Back"
	rect 220 260 200 24
	textalign ITEM_ALIGN_CENTER
	textalignx 100
	textaligny 17
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

    # ----------------------------------------------------------------
    # 3. settings_aimassist_advanced.menu
    # ----------------------------------------------------------------
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
	name aim_subtitle
	style 1
	text "Interpolate ON for online, OFF for bots. Snap locks near targets."
	rect 60 32 520 18
	textalign ITEM_ALIGN_CENTER
	textalignx 260
	textaligny 14
	textscale .22
	forecolor .8 .8 .8 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_YESNO
	text "Interpolate Position (online):"
	cvar "cg_handheldAimAssistInterpolate"
	rect 80 55 220 20
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
	text "Unlagged-Sync (Auto-Lead):"
	cvar "cg_handheldAimAssistUnlaggedSync"
	rect 80 80 220 20
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
	rect 80 105 220 20
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
	text "Pitch Strength Multiplier:"
	cvarfloat "cg_handheldAimAssistPitch" 0.75 0.30 1.50
	rect 80 130 220 20
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
	text "Sticky Target (frames):"
	cvarfloat "cg_handheldAimAssistSticky" 15 0 30
	rect 80 155 220 20
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
	text "Snap Angle (degrees):"
	cvarfloat "cg_handheldAimAssistSnapAngle" 3 0 10
	rect 80 180 220 20
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
	rect 80 205 220 20
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
	rect 80 230 220 20
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
	name aim_hint1
	style 1
	text "Snap: stronger pull when crosshair is within Snap Angle."
	rect 60 260 520 16
	textalign ITEM_ALIGN_CENTER
	textalignx 260
	textaligny 12
	textscale .2
	forecolor .7 .7 .7 1
	visible 1
	decoration
}

itemDef {
	name aim_options
	group grpAim
	type ITEM_TYPE_BUTTON
	text "Back"
	rect 220 290 200 24
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

    # ----------------------------------------------------------------
    # 4. menus.txt
    # ----------------------------------------------------------------
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
        print("==> Patching SmokinGuns")
        diagnostic_dump()
        if patch_makefile(): applied += 1
        patch_q_platform()
        patch_client_cvar()
        patch_ui_cvar()
        patch_aim_assist()
        write_menu_override()
    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints(): applied += 1
    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()