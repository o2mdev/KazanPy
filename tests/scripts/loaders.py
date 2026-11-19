import sys, struct
from pathlib import Path
import numpy as np
S = Path(sys.argv[1]); D = S / 'ld'; D.mkdir(exist_ok=True)
from kazan.io import loaders
L = loaders.load
def show(name, r):
    ax, y, dsc = r
    print(f'{name:12s}', np.shape(y), np.asarray(y).dtype, 'x', np.round(np.ravel(ax.x)[[0, -1]], 6).tolist() if ax.get('x') is not None and len(np.ravel(ax.x)) else None,
          '|', ax.get('xlabel'), '|', ax.get('ylabel'), '| y0', np.round(np.ravel(y)[0], 4))
# ---- real text files
show('csv ,', L('C:/Temp/21-y - 50.csv', '*', 'ASCII', [',', 3, 'Time, s']))
show('csv Y', L('C:/Temp/21-y - 50.csv', '*', 'ASCII', [',', 1, '']))
show('tab hdr', L('C:/Temp/LANL/200mmpole_IB_trace_nextday.csv', '*', 'ASCII', ['\t', 3, 'Current, A']))
show('dat space', L('C:/Temp/Denver/mytest.dat', '*.dat', 'ASCII', [' ', 3, 'Field, G']))
show('dat rY,iY', L('C:/Temp/Jens/031208/e3120801.dat', '*.dat', 'ASCII', [' ', 2, '']))
# layouts on a synthetic file: idx, X, rY, iY
t = np.arange(5.0)
np.savetxt(D / 'l6.txt', np.column_stack([t + 1, t * 0.1, t, -t]), delimiter='\t')
show('idx,X,rY,iY', L(D / 'l6.txt', '*.txt', 'ASCII', ['\t', 6, 'T, s']))
np.savetxt(D / 'l4.txt', np.column_stack([t, t, -t, 2 * t, -2 * t]), delimiter=';')
show('X,(rY,iY)n', L(D / 'l4.txt', '*.txt', 'ASCII', [';', 4, '']))
show('X,(rY)n,(iY)n', L(D / 'l4.txt', '*.txt', 'ASCII', [';', 8, '']))
(D / 'foot.txt').write_text('1\t2\t3\n2\t4\t6\n; created by Kazan Viewer 3.0\n; ax.xlabel: Field, G\n; ax.y: 7 8\n; freq1: 9.5e9\n')
r = L(D / 'foot.txt', '*.txt', 'ASCII', ['\t', 3, '']); show('footer', r); print('   footer ax.y', r[0].get('y'), r[0].get('freq1'))
p = np.arange(24.0); np.savetxt(D / 'a2d.txt', p)
show('ASCII2D', L(D / 'a2d.txt', '*.txt', 'ASCII2D', [True, 1, '4 3 1e-6 2e-6 0']))
# ---- image
show('image', L('C:/Temp/2026-05-20_103310.jpg', '*.jpg', 'image'))
# ---- SpecMan variants on a real file
f = 'C:/Temp/BE/2025/02/250217/2064file.d01'
for st in ('SpecMan', 'SpecManNIST', 'SpecManFLD'):
    r = L(f, '*.d01', st); show(st, r); print('   data streams', [np.shape(d) for d in r[0].get('data') or []], r[2].KAZANformat)
# ---- synthetic binaries in the MATLAB layouts
n = 8; z = np.arange(n) + 1j * np.arange(n)[::-1]
hdr = struct.pack('>bi4d', 1, n, 1e-6, 2e-6, 100e6, 0) + b'comment'.ljust(1024, b'\0')
(D / 'a.rmn').write_bytes(hdr + np.column_stack([z.real, z.imag]).astype('>f4').tobytes())
show('RMN_1D', L(D / 'a.rmn', '*.rmn', 'RMN_1D'))
n1, n2 = 3, 2
hdr = struct.pack('>bi4di4d', 4, n2, 1e-3, 0, 0, 0, n1, 1e-6, 0, 0, 0) + b'\0' * 1024
zz = (np.arange((n1 + 1) * (n2 + 1)) * (1 + 1j))
(D / 'b.rmn').write_bytes(hdr + np.column_stack([zz.real, zz.imag]).astype('>f4').tobytes())
r = L(D / 'b.rmn', '*.rmn', 'RMN_2D', ['2DTF', 1, '']); show('RMN_2D TF', r); print('   y axis', r[0].y, r[0].ylabel)
np.savetxt(D / 'r.dat', np.column_stack([np.arange(4.0), -np.arange(4.0)]).ravel())
show('RMNdat', L(D / 'r.dat', '*.dat', 'RMNdat'))
# TecMag
b = bytearray(2048); struct.pack_into('>ib', b, 0, 1, 0); struct.pack_into('>i', b, 50, n)
struct.pack_into('>7d', b, 154, 1.0, 42.5, 1e5, 1e-6, 0.1, 0, 0); b[1024:1030] = b'hello\n'
(D / 't.tnt').write_bytes(bytes(b) + np.column_stack([z.imag, z.real]).astype('>f4').tobytes())
r = L(D / 't.tnt', '*', 'TecMag'); show('TecMag', r); print('   ', r[2].c1, r[2].frequency1)
# XWINNMR fid / WINNMR
x = D / 'xw'; x.mkdir(exist_ok=True)
(x / 'acqus').write_text('##TITLE= t\n##$TD= 16\n##$SW_h= 1000\n##$BYTORDA= 0\n##$BF1= 300.1\n')
(x / 'fid').write_bytes(np.column_stack([np.arange(8), -np.arange(8)]).astype('<i4').tobytes())
(x / 'title').write_text('my title\n')
r = L(x / 'fid', '*', 'XWINNMR'); show('XWINNMR', r); print('   ', r[0].title, r[0].freq1)
(D / 'w.aqs').write_text('##$AQ_mod= 3\n##$TD= 8\n##$SW_h= 800\n##$BYTORDA= 0\n##$O1= 10\n')
np.arange(8, dtype='<f4').tofile(D / 'w.1r'); (-np.arange(8, dtype='<f4')).tofile(D / 'w.1i')
show('WINNMR', L(D / 'w.aqs', '*.aqs', 'WINNMR'))
sp = D / 'ss'; sp.mkdir(exist_ok=True); (sp / 'acq').write_text('al=4\ndw=2u\n')
np.concatenate([np.arange(4), -np.arange(4)]).astype('>f4').tofile(sp / 'data')
show('Spinsight', L(sp / 'data', '*', 'Spinsight'))
# Astashkin
(D / 'as.par').write_text('X Axis Resolution [pts]: 3\nY Axis Resolution [pts]: 2\nField Sweep Coordinate: N\nRF1 Sweep Coordinate: N\nInitial delay: 100\nDelay step X: 10\n')
(D / 'as.dat').write_bytes(b'\0' * 8 + np.arange(6, dtype='<f4').tobytes())
show('ASTASHKIN', L(D / 'as.par', '*.par', 'ASTASHKIN'))
# JSS
(D / 'j.par').write_text('JSS 2\nRES 8\nHCF 3400\nHSW 100\nMF 9.5\n')
np.arange(8, dtype='>i4').tofile(D / 'j.spc')
r = L(D / 'j.par', '*.par', 'XEPR_JSS'); show('XEPR_JSS', r); print('   freq1', r[0].freq1)
# missing
for st in ('UofC_bin', 'WEBMOSS'):
    try: L(D / 'j.par', '*', st)
    except NotImplementedError as e: print(st, '->', e)
print('OK')
