import os
import re
import subprocess
import urllib.request
import urllib.parse
import html.parser

class DirectoryParser(html.parser.HTMLParser):
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
                    elif value.lower().endswith(('.pk3', '.cfg', '.dat', '.txt', '.wad')):
                        self.files.append(value)

def patch_makefile(filepath="Makefile"):
    if not os.path.exists(filepath):
        print(f"Error: Makefile not found at {filepath}")
        return False
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    content = re.sub(r'ARCH\s*\?=\s*.*', 'ARCH ?= aarch64', content)
    content = re.sub(r'BUILD_GAME_SO\s*\?=\s*.*', 'BUILD_GAME_SO ?= 1', content)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return True

def inject_neon_math(filepath="code/qcommon/q_math.c"):
    if not os.path.exists(filepath):
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
        new_content, n = re.subn(
            r'(float\s+Q_rsqrt\s*\(\s*float\s+number\s*\)\s*\{)',
            neon_code + r'\1', content, count=1)
        if n == 0:
            print("[WARN] Q_rsqrt-Signatur nicht gefunden - NEON-Injection uebersprungen, Original unveraendert.")
            return
        new_content, n = re.subn(
            r'(float\s+Q_rsqrt.*?return.*?\}\n)', r'\1#endif\n',
            new_content, flags=re.DOTALL, count=1)
        if n == 0:
            print("[WARN] Ende von Q_rsqrt nicht gefunden - #endif fehlt, Datei NICHT geschrieben (waere ungueltiges C).")
            return
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("[PATCHED] NEON-Version von Q_rsqrt eingefuegt - bitte q_math.c manuell gegenpruefen.")

def inject_openmp_simd(filepath, target_string):
    if not os.path.exists(filepath):
        return
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if "#pragma omp simd" not in content and target_string in content:
        content = content.replace(target_string, f"#pragma omp simd aligned(vertices: 16)\n\t{target_string}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

def crawl_and_download_mirror(base_url, target_base_dir, current_subpath=""):
    active_url = urllib.parse.urljoin(base_url, current_subpath)
    try:
        req = urllib.request.Request(active_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
        parser = DirectoryParser()
        parser.feed(html_content)
        local_dir = os.path.join(target_base_dir, current_subpath)
        os.makedirs(local_dir, exist_ok=True)
        for filename in sorted(list(set(parser.files))):
            file_url = urllib.parse.urljoin(active_url, filename)
            dest_path = os.path.join(local_dir, filename)
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                continue
            urllib.request.urlretrieve(file_url, dest_path)
        for subdir in sorted(list(set(parser.subdirs))):
            clean_subdir = subdir.lstrip('/')
            next_subpath = os.path.join(current_subpath, clean_subdir)
            crawl_and_download_mirror(base_url, target_base_dir, next_subpath)
    except Exception as e:
        print(f"Error crawling {active_url}: {e}")

if __name__ == '__main__':
    # Verhindert das "dubious ownership"-Git-Problem proaktiv, statt sich
    # darauf zu verlassen, dass es zufaellig nicht-fatal bleibt.
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "/work"], check=False)

    patch_makefile('Makefile')
    inject_neon_math('code/qcommon/q_math.c')
    inject_openmp_simd('code/renderer/tr_mesh.c', 'for ( i = 0 ; i < numVerts ; i++ )')
    inject_openmp_simd('code/game/bg_pmove.c', 'for ( i = 0 ; i < pml.numtouch ; i++ )')

    cpu_count = os.cpu_count() or 2

    # CC kann von aussen (YAML) auf "ccache gcc" gesetzt werden, um
    # wiederholte CI-Laeufe schneller zu machen. Das beschleunigt NUR den
    # Build selbst, nicht die Laufzeit-Performance auf dem Handheld -
    # beides sind unabhaengige Dinge.
    cc = os.environ.get("CC", "cc")

    # -mearly-ra=all entfernt: keine gueltige GCC-Option, war der
    # urspruengliche Build-Abbruch ("unrecognized command line option").
    #
    # -mno-outline-atomics: vermeidet Laufzeit-Bibliotheksaufrufe fuer
    #   Atomic-Operationen (Cortex-A35 hat ohnehin keine LSE-Atomics,
    #   die IFUNC-Indirektion dafuer ist damit reiner Overhead).
    # -funroll-loops: hilft bei kleinen, haeufig durchlaufenen
    #   Engine-Loops, kostet aber Code-Groesse (mehr I-Cache-Druck) -
    #   bei 1GB RAM im Zweifel testen und bei Verschlechterung entfernen.
    # BUILD_GAME_QVM=0: explizit auf der Kommandozeile erzwungen (nicht
    #   nur ueber die Makefile-Regex), damit garantiert die nativen
    #   .so-Module gebaut werden - offiziell dokumentierter Weg laut
    #   ioquake3.org/help/players-guide (+set vm_cgame 0 usw. zur
    #   Laufzeit ist das Gegenstueck dazu, das gehoert ins Launch-Script,
    #   nicht hierhin).
    #
    # BEWUSST NICHT ergaenzt:
    # -flto - in einer frueheren Runde dieses Projekts explizit als
    #   Ursache fuer ARM64-Abstuerze bei ioquake3-Engines dokumentiert.
    #   Nicht ohne gezielten, isolierten Test hinzufuegen.
    # -mfpu=... - reine ARM32-Flag, unter AArch64 ungueltig (NEON ist
    #   dort bereits verpflichtender Architekturteil, keine Aktivierung
    #   noetig).
    # Profile-Guided Optimization (PGO) - braeuchte echte Laufzeitprofile
    #   vom Handheld selbst, in einer CI-Umgebung ohne das Zielgeraet
    #   nicht sinnvoll umsetzbar.
    compile_cmd = (
        f"make -j{cpu_count} ARCH=aarch64 BUILD_GAME_SO=1 BUILD_GAME_QVM=0 CC=\"{cc}\" "
        f"OPTIMIZE=\"-O3 -mcpu=cortex-a35 -mtune=cortex-a35 -pipe -fomit-frame-pointer -ffast-math "
        f"-ftree-vectorize -fno-math-errno -fno-trapping-math -fno-semantic-interposition -fno-plt "
        f"-fno-exceptions -fno-rtti -fno-stack-protector -fno-asynchronous-unwind-tables -fmerge-all-constants "
        f"-falign-functions=16 -falign-loops=16 -DNDEBUG -w -fcommon -fopenmp-simd -flax-vector-conversions "
        f"-mno-outline-atomics -funroll-loops\" "
        f"LDFLAGS=\"-Wl,-O1 -Wl,--as-needed -Wl,--strip-all\""
    )
    print(f"[INFO] Kompiliere mit CC={cc}, {cpu_count} parallele Jobs")
    subprocess.run(compile_cmd, shell=True, check=True)

    mirror_root = "http://download.smokin-guns.org/mirror.9k.lv/smokinguns/smokinguns/"
    output_mod_dir = "build/release-linux-aarch64/smokinguns"
    crawl_and_download_mirror(mirror_root, output_mod_dir)
