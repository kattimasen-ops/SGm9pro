import os
import re

def patch_makefile(filepath="Makefile"):
    """Your original baseline Makefile patcher for AArch64 and game shared libraries."""
    if not os.path.exists(filepath):
        print(f"Error: Makefile not found at {filepath}")
        return
        
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Enforce aarch64 target definitions and shared library compilation
    content = re.sub(r'ARCH\s*\?=\s*.*', 'ARCH ?= aarch64', content)
    content = re.sub(r'BUILD_GAME_SO\s*\?=\s*.*', 'BUILD_GAME_SO ?= 1', content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Makefile successfully patched for AArch64.")

def inject_neon_math(filepath="code/qcommon/q_math.c"):
    """Replaces legacy float calculations with Cortex-A35 hardware NEON instructions."""
    if not os.path.exists(filepath):
        print(f"Notice: {filepath} not found, skipping NEON math injection.")
        return
        
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    if "arm_neon.h" not in content:
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
        content = re.sub(r'(float\s+Q_rsqrt\s*\(\s*float\s+number\s*\)\s*\{)', neon_code + r'\1', content, count=1)
        content = re.sub(r'(float\s+Q_rsqrt.*?return.*?\}\n)', r'\1#endif\n', content, flags=re.DOTALL, count=1)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Injected ARM NEON hardware math intrinsics into {filepath}")

def inject_openmp_simd(filepath, target_string):
    """Forces OpenMP SIMD vectorization on heavy loops for the RK3326 processor."""
    if not os.path.exists(filepath):
        print(f"Notice: {filepath} not found, skipping OpenMP SIMD injection.")
        return
        
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    if "#pragma omp simd" not in content and target_string in content:
        content = content.replace(target_string, f"#pragma omp simd aligned(vertices: 16)\n\t{target_string}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Injected OpenMP SIMD pragma vectorization into {filepath}")

if __name__ == '__main__':
    # 1. Run your baseline Makefile modification
    patch_makefile('Makefile')
    
    # 2. Stack high-performance hardware micro-optimizations directly into source files
    inject_neon_math('code/qcommon/q_math.c')
    inject_openmp_simd('code/renderer/tr_mesh.c', 'for ( i = 0 ; i < numVerts ; i++ )')
    inject_openmp_simd('code/game/bg_pmove.c', 'for ( i = 0 ; i < pml.numtouch ; i++ )')
