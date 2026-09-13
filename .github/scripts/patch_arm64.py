import os
import re

def find_file(filename, start_dir="."):
    """Recursively search for files across the entire repository to avoid layout assumptions."""
    for root, dirs, files in os.walk(start_dir):
        if filename in files:
            return os.path.join(root, filename)
    return None

def patch_makefile():
    makefile_path = find_file("Makefile")
    if not makefile_path:
        print("Error: Makefile could not be found in the workspace.")
        return None
        
    print(f"Discovered Makefile at: {makefile_path}")
    with open(makefile_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Enforce aarch64 target definitions and game shared library compilation
    content = re.sub(r'ARCH\s*\?=\s*.*', 'ARCH ?= aarch64', content)
    content = re.sub(r'BUILD_GAME_SO\s*\?=\s*.*', 'BUILD_GAME_SO ?= 1', content)
    
    with open(makefile_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Makefile successfully patched for AArch64.")
    return os.path.dirname(makefile_path)

def inject_neon_math():
    q_math_path = find_file("q_math.c")
    if not q_math_path:
        print("Notice: q_math.c not found, skipping NEON math injection.")
        return
        
    with open(q_math_path, 'r', encoding='utf-8', errors='ignore') as f:
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
        
        with open(q_math_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Injected ARM NEON hardware math intrinsics into {q_math_path}")

def inject_openmp_simd(target_filename, target_string):
    filepath = find_file(target_filename)
    if not filepath:
        print(f"Notice: {target_filename} not found, skipping OpenMP SIMD injection.")
        return
        
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    if "#pragma omp simd" not in content and target_string in content:
        content = content.replace(target_string, f"#pragma omp simd aligned(vertices: 16)\n\t{target_string}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Injected OpenMP SIMD pragma vectorization into {filepath}")

if __name__ == '__main__':
    # Dynamically locate and patch build files
    build_dir = patch_makefile()
    
    # Inject high-performance hardware micro-optimizations
    inject_neon_math()
    inject_openmp_simd('tr_mesh.c', 'for ( i = 0 ; i < numVerts ; i++ )')
    inject_openmp_simd('bg_pmove.c', 'for ( i = 0 ; i < pml.numtouch ; i++ )')
    
    # Cache the target compilation directory path for the GitHub workflow runner
    if build_dir:
        with open(".build_dir", "w", encoding='utf-8') as f:
            f.write(build_dir)
