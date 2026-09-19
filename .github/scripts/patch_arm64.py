#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

[EXTENDED] Handheld aim assist v4 mit Menü-Toggle:
  - S-Curve + Target Friction on cl.mouseDx/cl.mouseDy
  - Rotational Aim Magnetism + Fire-Assist on cl.viewangles
  - Line-of-Sight via CM_BoxTrace (SG-Signatur mit 8 Parametern)
  - Runtime toggle via cvar cg_handheldAimAssist
  - Menüpunkt in Settings -> Game Options -> Performance
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
        content = content.replace(
            "$(B)/$(BASENAME)/ui/",
            "$(B)/$(BASEGAME)/ui/"
        )
        print("[PATCHED] Makefile: Corrected BASENAME -> BASEGAME in UI objects")

    sdl_include_line = "override CFLAGS += -I/usr/include/SDL\n"
    if "override CFLAGS += -I/usr/include/SDL" not in content:
        content = sdl_include_line + content
        print("[PATCHED] Makefile: added -I/usr/include/SDL to global CFLAGS")

    content = re.sub(r"\brm\s+(?!-)", "rm -f ", content)
    content = content.replace("python ", "python3 ")
    content = content.replace("python2 ", "python3 ")
    content = re.sub(r"-Werror[a-zA-Z0-9=-]*", "", content)
    content = re.sub(r"-Wmaybe-uninitialized", "", content)
    content = re.sub(r"-Wuninitialized", "", content)
    content = re.sub(r"-Wstrict-overflow", "", content)

    toxic_flags = [
        "-m32", "-m64",
        "-march=native", "march=native",
        "-msse", "-msse2", "-msse3", "-mfpmath=sse"
    ]
    for flag in toxic_flags:
        content = content.replace(flag, "")
    print("[PATCHED] Makefile: toxic x86 architecture flags removed")

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_q_platform():
    patched = 0
    if not os.path.isdir("code"):
        print("[WARN] code/ not found - skipping q_platform.h patches")
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

            changed = False
            pattern = re.compile(
                r'(#elif defined __arm__\s*\n#define ARCH_STRING "arm"\s*\n)'
            )
            new_content, n = pattern.subn(
                r'\1#elif defined __aarch64__\n#define ARCH_STRING "aarch64"\n',
                content,
            )
            if n > 0:
                content = new_content
                changed = True
            else:
                override = (
                    "/* [PATCHED] ARM64 ARCH_STRING override */\n"
                    "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
                    "#ifdef ARCH_STRING\n#undef ARCH_STRING\n#endif\n"
                    "#define ARCH_STRING \"aarch64\"\n"
                    "#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n"
                    "#endif\n\n"
                )
                content = override + content
                changed = True

            if changed:
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
        "/* [PATCHED] Define SDL_HINT_VIDEODRIVER and SDL_HINT_AUDIODRIVER\n"
        " * for SDL2 versions older than 2.0.22 where these hints were not\n"
        " * yet formalised as macros.\n"
        " */\n"
        "#ifndef SDL_HINT_VIDEODRIVER\n"
        "#define SDL_HINT_VIDEODRIVER \"SDL_VIDEODRIVER\"\n"
        "#endif\n"
        "#ifndef SDL_HINT_AUDIODRIVER\n"
        "#define SDL_HINT_AUDIODRIVER \"SDL_AUDIODRIVER\"\n"
        "#endif\n"
        "\n"
    )

    content = patch + content

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] sdl12-compat: SDL_HINT_* fallbacks inserted at top of file")
    return True


# =====================================================================
# Client-Cvar-Registrierung in cl_main.c
# =====================================================================
def patch_client_cvar():
    """Registriert cg_handheldAimAssist in CL_Init() von cl_main.c."""
    path = os.path.join("code", "client", "cl_main.c")
    if not os.path.exists(path):
        print("[WARN] cl_main.c not found - skipping client cvar registration")
        return False

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if 'cg_handheldAimAssist' in content:
        print(f"[SKIP] Client cvar already registered in {path}")
        return True

    anchor = 'j_up_axis =      Cvar_Get ("j_up_axis",      "2", CVAR_ARCHIVE);'
    if anchor not in content:
        print("[WARN] cl_main.c anchor not found - skipping client cvar")
        return False

    insertion = (
        anchor + "\n"
        "\t/* [PATCHED] Handheld Aim Assist toggle */\n"
        "\tCvar_Get (\"cg_handheldAimAssist\", \"1\", CVAR_ARCHIVE);"
    )
    content = content.replace(anchor, insertion, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] {path}: cg_handheldAimAssist registered in CL_Init()")
    return True


# =====================================================================
# UI-Cvar-Registrierung in ui_local.h + ui_main.c
# =====================================================================
def patch_ui_cvar():
    """Registriert ui_handheldAimAssist in der UI-VM."""
    # --- ui_local.h ---
    ui_local_path = None
    for root, _dirs, files in os.walk("code"):
        if "ui_local.h" in files:
            ui_local_path = os.path.join(root, "ui_local.h")
            break

    if ui_local_path:
        with open(ui_local_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "ui_handheldAimAssist" not in content:
            anchor = "extern vmCvar_t\tui_brassTime;"
            if anchor in content:
                content = content.replace(
                    anchor,
                    "extern vmCvar_t\tui_handheldAimAssist;\n" + anchor,
                    1
                )
                with open(ui_local_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"[PATCHED] {ui_local_path}: extern ui_handheldAimAssist added")
            else:
                print("[WARN] ui_local.h anchor not found")

    # --- ui_main.c ---
    ui_main_path = None
    for root, _dirs, files in os.walk("code"):
        if "ui_main.c" in files:
            ui_main_path = os.path.join(root, "ui_main.c")
            break

    if not ui_main_path:
        print("[WARN] ui_main.c not found - skipping ui cvar registration")
        return False

    with open(ui_main_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "ui_handheldAimAssist;" not in content:
        anchor = "vmCvar_t\tui_brassTime;"
        if anchor in content:
            content = content.replace(
                anchor,
                "vmCvar_t\tui_handheldAimAssist;\n" + anchor,
                1
            )

    if '"cg_handheldAimAssist"' not in content:
        anchor = '\t{ &ui_brassTime, "cg_brassTime", "2500", CVAR_ARCHIVE },'
        if anchor in content:
            entry = '\n\t{ &ui_handheldAimAssist, "cg_handheldAimAssist", "1", CVAR_ARCHIVE },'
            content = content.replace(anchor, anchor + entry, 1)

    with open(ui_main_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] {ui_main_path}: ui_handheldAimAssist cvar registered")
    return True


# =====================================================================
# Handheld Aim Assist v4 mit Cvar-Abfrage
# =====================================================================
def patch_aim_assist():
    """Injiziert die Aim-Assist-Hooks in cl_input.c (v4 mit Cvar)."""
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cl_input.c" in files:
            target_file = os.path.join(root, "cl_input.c")
            break

    if not target_file or not os.path.exists(target_file):
        print("[WARN] cl_input.c not found - skipping aim assist patch")
        return False

    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "CL_HandheldInputCurve" in content:
        print(f"[SKIP] Aim assist already present in {target_file}")
        return True

    helper_code = r"""
/* ============================================================
 * [PATCHED] Handheld Aim Assist v4 + Menue-Toggle
 * ============================================================
 *  Wird ueber cvar cg_handheldAimAssist gesteuert.
 *  Bei "0" tun beide Hooks nichts.
 * ============================================================ */
#include <math.h>

#ifndef ET_PLAYER
#define ET_PLAYER 1
#endif

#ifndef EF_DEAD
#define EF_DEAD 0x00000001
#endif

#define HHA_PI                3.14159265358979323846f
#define HHA_MAX_ANGLE        15.0f
#define HHA_FALLOFF_ANGLE     7.0f
#define HHA_MAGNETISM_YAW     0.24f
#define HHA_MAGNETISM_PITCH   0.15f
#define HHA_FIRE_YAW          0.45f
#define HHA_FIRE_PITCH        0.28f
#define HHA_FRICTION          0.75f
#define HHA_FRICTION_MAX_MAG 40.0f
#define HHA_CURVE_EXP         1.05f
#define HHA_CURVE_REF        32.0f
#define HHA_STICKY_FRAMES    10
#define HHA_MAX_DIST         4096.0f
#define HHA_MIN_DIST           48.0f
#define HHA_CHEST_HEIGHT     32.0f

static int hha_lastTargetNum = -1;
static int hha_lastTargetAge = 0;

static int      hha_cachedTarget   = -1;
static float    hha_cachedAngle    = 999.0f;
static vec3_t   hha_cachedDir      = { 0, 0, 0 };
static qboolean hha_cachedValid    = qfalse;

static qboolean HHA_IsEnabled( void ) {
    return ( Cvar_VariableIntegerValue("cg_handheldAimAssist") != 0 );
}

static qboolean HHA_HasLineOfSight( const vec3_t fromFeet, const vec3_t toFeet ) {
    trace_t tr;
    vec3_t  eye, chest;

    eye[0] = fromFeet[0];
    eye[1] = fromFeet[1];
    eye[2] = fromFeet[2] + cl.snap.ps.viewheight;

    chest[0] = toFeet[0];
    chest[1] = toFeet[1];
    chest[2] = toFeet[2] + HHA_CHEST_HEIGHT;

    CM_BoxTrace( &tr, eye, chest, NULL, NULL, 0, CONTENTS_SOLID, 0 );

    return ( tr.fraction >= 0.999f );
}

static int HHA_FindTarget( vec3_t bestDir, float *bestAngleOut ) {
    int    i, best = -1;
    float  bestAngle = HHA_MAX_ANGLE;
    vec3_t forward, toEnt;

    *bestAngleOut = 999.0f;

    if ( clc.state != CA_ACTIVE )
        return -1;
    if ( cl.snap.numEntities <= 0 )
        return -1;

    AngleVectors( cl.viewangles, forward, NULL, NULL );

    for ( i = 0; i < cl.snap.numEntities; i++ ) {
        entityState_t *ent = &cl.parseEntities[
            ( cl.snap.parseEntitiesNum + i ) & ( MAX_PARSE_ENTITIES - 1 ) ];
        float dx, dy, dz, distSq, dot, angle;

        if ( ent->eType != ET_PLAYER )
            continue;
        if ( ent->number == cl.snap.ps.clientNum )
            continue;
        if ( ent->eFlags & EF_DEAD )
            continue;

        dx = ent->pos.trBase[0] - cl.snap.ps.origin[0];
        dy = ent->pos.trBase[1] - cl.snap.ps.origin[1];
        dz = ent->pos.trBase[2] - cl.snap.ps.origin[2];
        distSq = dx*dx + dy*dy + dz*dz;

        if ( distSq < HHA_MIN_DIST * HHA_MIN_DIST ) continue;
        if ( distSq > HHA_MAX_DIST * HHA_MAX_DIST ) continue;

        toEnt[0] = dx; toEnt[1] = dy; toEnt[2] = dz;
        VectorNormalize( toEnt );

        dot = DotProduct( forward, toEnt );
        if ( dot >  1.0f ) dot =  1.0f;
        if ( dot < -1.0f ) dot = -1.0f;
        angle = acosf( dot ) * ( 180.0f / HHA_PI );

        if ( ent->number == hha_lastTargetNum && angle < HHA_MAX_ANGLE + 5.0f ) {
            angle *= 0.65f;
        }

        if ( angle < bestAngle ) {
            if ( !HHA_HasLineOfSight( cl.snap.ps.origin, ent->pos.trBase ) ) {
                continue;
            }
            bestAngle = angle;
            best      = ent->number;
            VectorCopy( toEnt, bestDir );
        }
    }

    *bestAngleOut = bestAngle;
    return best;
}

static void HHA_UpdateCachedTarget( void ) {
    hha_cachedTarget = HHA_FindTarget( hha_cachedDir, &hha_cachedAngle );
    hha_cachedValid  = qtrue;

    if ( hha_cachedTarget >= 0 ) {
        hha_lastTargetNum = hha_cachedTarget;
        hha_lastTargetAge = 0;
    } else if ( ++hha_lastTargetAge > HHA_STICKY_FRAMES ) {
        hha_lastTargetNum = -1;
    }
}

static void CL_HandheldInputCurve( void ) {
    int   *mx_raw;
    int   *my_raw;
    float  mag;
    float  friction = 1.0f;

    if ( !HHA_IsEnabled() ) {
        return;
    }

    HHA_UpdateCachedTarget();

    mx_raw = &cl.mouseDx[cl.mouseIndex];
    my_raw = &cl.mouseDy[cl.mouseIndex];

    mag = sqrtf( (float)(*mx_raw * *mx_raw) + (float)(*my_raw * *my_raw) );

    if ( hha_cachedTarget >= 0 && mag > 0.0f && mag < HHA_FRICTION_MAX_MAG ) {
        friction = HHA_FRICTION;
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
    vec3_t forward, targetAngles;
    float  dot, currentAngle, yawDiff, pitchDiff, strength;
    float  magYaw, magPitch;
    qboolean firing;

    if ( !HHA_IsEnabled() ) {
        return;
    }

    if ( clc.state != CA_ACTIVE )
        return;
    if ( !hha_cachedValid || hha_cachedTarget < 0 )
        return;

    AngleVectors( cl.viewangles, forward, NULL, NULL );
    dot = DotProduct( forward, hha_cachedDir );
    if ( dot >  1.0f ) dot =  1.0f;
    if ( dot < -1.0f ) dot = -1.0f;
    currentAngle = acosf( dot ) * ( 180.0f / HHA_PI );

    if ( currentAngle > HHA_MAX_ANGLE )
        return;

    firing = ( cmd && ( cmd->buttons & BUTTON_ATTACK ) );
    magYaw   = firing ? HHA_FIRE_YAW   : HHA_MAGNETISM_YAW;
    magPitch = firing ? HHA_FIRE_PITCH : HHA_MAGNETISM_PITCH;

    vectoangles( hha_cachedDir, targetAngles );

    yawDiff   = targetAngles[YAW]   - cl.viewangles[YAW];
    pitchDiff = targetAngles[PITCH] - cl.viewangles[PITCH];

    while ( yawDiff   >  180.0f ) yawDiff   -= 360.0f;
    while ( yawDiff   < -180.0f ) yawDiff   += 360.0f;
    while ( pitchDiff >  180.0f ) pitchDiff -= 360.0f;
    while ( pitchDiff < -180.0f ) pitchDiff += 360.0f;

    if ( currentAngle <= HHA_FALLOFF_ANGLE ) {
        strength = 1.0f;
    } else {
        strength = 1.0f - ( currentAngle - HHA_FALLOFF_ANGLE ) /
                          ( HHA_MAX_ANGLE - HHA_FALLOFF_ANGLE );
        if ( strength < 0.0f ) strength = 0.0f;
    }

    cl.viewangles[YAW]   += yawDiff   * magYaw   * strength;
    cl.viewangles[PITCH] += pitchDiff * magPitch * strength;
}
/* ============================================================ */
"""

    mouse_body_pat = re.compile(
        r'(void\s+CL_MouseMove\s*\(\s*usercmd_t\s*\*\s*cmd\s*\)\s*\{)'
    )
    if not mouse_body_pat.search(content):
        print("[WARN] CL_MouseMove not found - skipping aim assist")
        return False

    content = mouse_body_pat.sub(
        lambda m: (helper_code
                   + "\n" + m.group(1)
                   + "\n\tCL_HandheldInputCurve();"),
        content, count=1
    )

    joy_pat = re.compile(
        r'(\n[ \t]*CL_JoystickMove\s*\(\s*&\s*cmd\s*\)\s*;)'
    )
    if not joy_pat.search(content):
        print("[WARN] CL_JoystickMove call not found - skipping magnetism hook")
        return False

    content = joy_pat.sub(
        lambda m: m.group(1) + "\n\n\tCL_HandheldAimMagnetism( &cmd );",
        content, count=1
    )

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Aim assist v4 mit Cvar in {target_file}")
    return True


# =====================================================================
# Menu-Override als lose Datei ins Artefakt schreiben
# =====================================================================
def write_menu_override():
    """Schreibt die modifizierte settings_options.menu ins Artefakt."""
    if not os.path.exists("Makefile"):
        return False

    rel_dir = os.path.join("build", "release-linux-aarch64")
    menu_dir = os.path.join(rel_dir, "smokinguns", "ui")
    os.makedirs(menu_dir, exist_ok=True)

    menu_file = os.path.join(menu_dir, "settings_options.menu")

    content = r"""#include "ui/menudef.h"
#define ROW1 80
#define ROW2 330
#define ROW3 200

{
\\ SETUP MENU \\

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
      		textalig
