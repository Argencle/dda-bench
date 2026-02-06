# pipobj_to_ifdda_dense_simple.py
import re

# ====== A MODIFIER ======
inp = "bin/shape.dat"
out = "bin/shape_ifdda.dat"

aretecube_override = 1.4048319255318794e-08  # d en mètres
eps_obj = (1.69, 0.20)  # epsilon objet (re, im)
eps_bg = (1.00, 0.00)  # epsilon background (re, im)
# =======================


def fortran_cplx(re_im):
    re_, im_ = re_im
    return f"({re_: .16e},{im_: .16e})"


lines = open(inp, "r", encoding="utf-8", errors="ignore").read().splitlines()

# lattice spacings (dx,dy,dz)/d (optionnel ici, souvent =1 1 1)
dx = dy = dz = None
for ln in lines:
    if "lattice spacings" in ln:
        nums = re.findall(r"[-+]?\d+\.\d+E[-+]?\d+|[-+]?\d+\.\d+|[-+]?\d+", ln)
        dx, dy, dz = map(float, nums[:3])
        break

# x0 y0 z0 (offset) en unités de d
x0 = y0 = z0 = None
for ln in lines:
    if (
        ("lattice offset" in ln or "zero dipole" in ln)
        and "x0" in ln
        or "zero dipole" in ln
    ):
        nums = re.findall(r"[-+]?\d+\.\d+E[-+]?\d+|[-+]?\d+\.\d+|[-+]?\d+", ln)
        if len(nums) >= 3:
            x0, y0, z0 = map(float, nums[:3])
            break

# NAT (optionnel)
nat = None
for ln in lines:
    m = re.search(r"^\s*([0-9]+)\s*=\s*NAT\b", ln)
    if m:
        nat = int(m.group(1))
        break

# start of table
start = None
for i, ln in enumerate(lines):
    if re.search(r"\bJA\b.*\bIX\b.*\bIY\b.*\bIZ\b", ln):
        start = i + 1
        break

# read occupied indices (peuvent être négatifs)
triples = []
for ln in lines[start:]:
    ln = ln.strip()
    if not ln:
        continue
    parts = ln.split()
    if len(parts) < 4:
        continue
    try:
        ix = int(parts[1])
        iy = int(parts[2])
        iz = int(parts[3])
    except:
        continue
    triples.append((ix, iy, iz))
    if nat is not None and len(triples) >= nat:
        break

occ = set(triples)

# bounding box sur les indices occupés
min_ix = min(t[0] for t in triples)
max_ix = max(t[0] for t in triples)
min_iy = min(t[1] for t in triples)
max_iy = max(t[1] for t in triples)
min_iz = min(t[2] for t in triples)
max_iz = max(t[2] for t in triples)

nx = max_ix - min_ix + 1
ny = max_iy - min_iy + 1
nz = max_iz - min_iz + 1

# pas d en mètres
a = float(aretecube_override)

# xs(1),ys(1),zs(1) doivent être en mètres et correspondre au coin (min_ix,min_iy,min_iz)
# x = (x0 + ix)*d
x_start = (x0 + min_ix) * a
y_start = (y0 + min_iy) * a
z_start = (z0 + min_iz) * a

eps_obj_s = fortran_cplx(eps_obj)
eps_bg_s = fortran_cplx(eps_bg)

with open(out, "w", encoding="utf-8") as f:
    f.write(f"{nx} {ny} {nz}\n")
    f.write(f"{a:.16e}\n")

    # positions: ordre Fortran i(z), j(y), k(x)
    for iz in range(nz):
        for iy in range(ny):
            for ix in range(nx):
                x = x_start + ix * a
                y = y_start + iy * a
                z = z_start + iz * a
                f.write(f"{x:.16e} {y:.16e} {z:.16e}\n")

    # epsilon: on teste l’occupation via indices originaux (IX,IY,IZ)
    for iz in range(nz):
        IZ = min_iz + iz
        for iy in range(ny):
            IY = min_iy + iy
            for ix in range(nx):
                IX = min_ix + ix
                f.write(
                    (eps_obj_s if (IX, IY, IZ) in occ else eps_bg_s) + "\n"
                )

print("written:", out)
print(
    "bbox IX:",
    (min_ix, max_ix),
    "IY:",
    (min_iy, max_iy),
    "IZ:",
    (min_iz, max_iz),
)
print("grid nx,ny,nz:", nx, ny, nz, "Ngrid=", nx * ny * nz, "Nocc=", len(occ))
print("x0,y0,z0 (in units of d):", x0, y0, z0)
print("start (m):", x_start, y_start, z_start, "aretecube (m):", a)
