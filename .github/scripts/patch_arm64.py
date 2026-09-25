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
 * [PATCHED v13.0] Handheld Aim Assist
 * FIX 1: EnsureCvars setzt Cvars NICHT mehr zwangsweise auf 1
 * FIX 2: Respawn-Reset zusaetzlich auf health-Wechsel
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
#define HHA_LOS_BUDGET        4
#define HHA_MAX_CANDIDATES   32
#define HHA_PULL_CAP_NORMAL 0.60f
#define HHA_PULL_CAP_SNAP   0.85f

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
static int      hha_cachedTarget = -1;
static float    hha_cachedAngle  = 999.0f;
static vec3_t   hha_cachedDir    = { 0, 0, 0 };
static qboolean hha_cachedValid  = qfalse;
static int      hha_losChecksThisFrame = 0;
static int      hha_lastSpawnCount = -1;
static int      hha_lastHealth = -999;

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
    if ( angle    > 45.0f )   angle    = 45.0f;
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
        Cvar_Set( "cg_handheldAimAssistTargetDist", "0" );
        return -1;
    }
    if ( cl.snap.numEntities <= 0 ) {
        Cvar_Set( "cg_handheldAimAssistTargetDist", "0" );
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

        if ( cfg->losEnabled ) {
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
            Cvar_Set( "cg_handheldAimAssistTargetDist",
                      va( "%.1f", (float)sqrt( (double)cands[i].distSq ) ) );
            return cands[i].entNum;
        }
    }

    Cvar_Set( "cg_handheldAimAssistTargetDist", "0" );
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

static void CL_HandheldUpdateTarget( void ) {
    hha_config_t cfg;
    int curSpawn;
    int curHealth;

    hha_losChecksThisFrame = 0;

    curSpawn  = cl.snap.ps.persistant[PERS_SPAWN_COUNT];
    curHealth = cl.snap.ps.stats[STAT_HEALTH];

    /* FIX 2: Respawn-Reset zusaetzlich auf Health-Wechsel.
     * Falls PERS_SPAWN_COUNT aus irgendeinem Grund nicht inkrementiert
     * (map_restart, manche Server-Mods), deckt der Health-Wechsel von
     * <=0 auf >0 den Respawn ab. */
    if ( curSpawn != hha_lastSpawnCount || 
         ( curHealth > 0 && hha_lastHealth <= 0 ) ) {
        int i;
        hha_lastSpawnCount = curSpawn;
        hha_lastHealth     = curHealth;
        hha_cachedValid    = qfalse;
        hha_cachedTarget   = -1;
        hha_lastTargetNum  = -1;
        hha_lastTargetAge  = 0;
        for ( i = 0; i < HHA_LOS_CACHE_SIZE; i++ ) {
            hha_los_cache[i].valid = qfalse;
        }
    }
    hha_lastHealth = curHealth;

    HHA_ReadConfig( &cfg );
    if ( !cfg.enabled ) {
        hha_cachedValid  = qfalse;
        hha_cachedTarget = -1;
        return;
    }
    HHA_UpdateCachedTarget( &cfg );
}

static void CL_HandheldInputCurve( void ) {
    hha_config_t cfg;
    int   *mx_raw, *my_raw;
    float  mag, friction = 1.0f;

    HHA_ReadConfig( &cfg );
    if ( !cfg.enabled ) return;

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
    float  magYaw, magPitch, pullYaw, pullPitch, cap;
    qboolean firing;
    qboolean inSnap;

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

    inSnap = ( currentAngle <= cfg.snapAngle && cfg.snapAngle > 0.0f );
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

    if ( currentAngle <= cfg.falloff ) {
        strength = 1.0f;
    } else {
        strength = 1.0f - ( currentAngle - cfg.falloff ) /
                          ( cfg.angle - cfg.falloff );
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
    print(f"[PATCHED] Aim assist v13.0 in {target_file}")
    return True
