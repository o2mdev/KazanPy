import sys
from pathlib import Path
import numpy as np
from kazan.core.data import KzData, Struct, verify
from kazan.io import loaders, writers
S = Path(sys.argv[1]) / 'wr'; S.mkdir(exist_ok=True)
x = np.linspace(3300, 3400, 501)
y1 = np.exp(-((x - 3350) / 5) ** 2) * 1e-3
d1 = verify(KzData(y=y1[:, None], ax=Struct(x=x, xlabel='Magnetic Field, G', title='test 1D', freq1=9.4e9), filename='a.dsc'))
t = np.linspace(0, 2e-6, 256); f = np.array([3340., 3350., 3360.])
y2 = np.exp(-t[:, None] / 5e-7) * (1 + 1j * f[None, :] / 3350)
d2 = verify(KzData(y=y2, ax=Struct(x=t, y=f, xlabel='Time, s', ylabel='Field, G', title='test 2D'), filename='b.d01'))

def chk(tag, kind, ext, d, subtype, rtol=1e-6):
    fn = S / f'{tag}.{ext}'
    writers.save(str(fn), d, kind)
    ax, y, dsc = loaders.load(str(fn), '*.' + ext, subtype)
    y = np.asarray(y)
    while y.ndim > 2 and y.shape[-1] == 1: y = y[..., 0]
    y = y[:, None] if y.ndim == 1 else y
    ok_y = y.shape == d.y.shape and np.allclose(y, d.y, rtol=rtol, atol=1e-12 + rtol * np.abs(d.y).max())
    ok_x = np.allclose(np.ravel(ax.x), np.ravel(d.ax.x), rtol=1e-6, atol=1e-12 * 0 + 1e-6 * np.ptp(d.ax.x))
    ok_ay = d.y.shape[1] == 1 or np.allclose(np.ravel(ax.y), np.ravel(d.ax.y))
    print(f'{tag:8s} {kind}: y {ok_y} x {ok_x} y-axis {ok_ay} | xlabel {ax.get("xlabel")!r}')
    assert ok_y and ok_x and ok_ay, tag

chk('d1_txt', 'txt', 'txt', d1, 'ASCII')
chk('d2_dat', 'dat', 'dat', verify(KzData(y=y2.real, ax=d2.ax, filename='b')), 'ASCII')
chk('d1_d01', 'd01', 'd01', d1, 'SpecMan', 1e-6)
chk('d2_d01', 'd01', 'd01', d2, 'SpecMan', 1e-6)
chk('d1_dsc', 'dsc', 'dsc', d1, 'XEPR')
chk('d2_dsc', 'dsc', 'dsc', d2, 'XEPR')
chk('d1_par', 'par', 'par', d1, 'XEPR', 1e-6)
try:
    writers.save(str(S / 'x.par'), d2, 'par'); print('2D par: no error!')
except ValueError as e:
    print('2D par refused:', e)
writers.save(str(S / 'd1.lmb'), d1, 'lmb')
lx, ly, com, strs = writers.lmb_read(str(S / 'd1.LMB'))
print('lmb: y', np.allclose(ly, y1, rtol=1e-6), 'x', np.allclose(lx, x, atol=1e-3), repr(com), strs[6:11])
assert np.allclose(ly, y1, rtol=1e-6) and np.allclose(lx, x, atol=1e-3)
# real file through d01 and dsc
ax, y, dsc = loaders.load(r'C:\Temp\Jens\110122\x122091301.DSC', '*.dsc', 'XEPR')
dr = verify(KzData(y=np.asarray(y), ax=Struct(ax), dsc=Struct(dsc), filename='x122091301.DSC'))
chk('real_d01', 'd01', 'd01', dr, 'SpecMan')
chk('real_dsc', 'dsc', 'dsc', dr, 'XEPR')
print('OK')
