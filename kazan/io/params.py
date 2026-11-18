"""Port of ``kv3_ParameterReader('load', ax, dsc)``: common parameters from dsc."""
from __future__ import annotations

import numpy as np

from ..core.data import Struct
from .units import getvalue


def parameter_reader(ax: Struct, dsc: Struct) -> Struct:
    for lab, key in (('xlabel', 'xunit'), ('ylabel', 'yunit')):
        text = str(ax.get(lab, ''))
        if ',' in text:
            ax[key] = text.split(',', 1)[1].strip()

    fmt = dsc.get('KAZANformat', '')
    if fmt == 'SPECMANTDMS':
        ax.title = dsc.get('name', '')
        bridge = dsc.get('devices_BRIDGE') or {}
        ax.freq1 = getvalue(str(bridge.get('Frequency', '0.0')))[0]
        ax.sample = dsc.get('sample_info_sample_info', '')
        if dsc.get('dconfig') == 'JIVA25CW.cfg':
            lin = dsc.get('devices_LIN') or {}
            b0 = getvalue(str(lin.get('ScanOffset', '0G')))[0] + 246.1
            b = getvalue(str(lin.get('ScanAmplitude', '5G')))[0]
            ax.freq1 = getvalue(str(bridge.get('Frequency', '670MHz')))[0]
            ax.x = b0 + np.linspace(-b / 2, b / 2, len(ax.x))
            ax.xlabel = 'Magnetic Field, G'
    elif fmt == 'SPECMAND01':
        if 'general_freq1' in dsc:
            ax.freq1 = getvalue(dsc.general_freq1)[0]
        ax.title = dsc.get('general_name', '')
        ax.sample = dsc.get('sample_info_sample_info_0', '')
        ax.comment = dsc.get('sample_info_sample_info_1', '')
    elif fmt == 'SPECMANNISTD01':
        if 'general_freq1' in dsc:
            ax.freq1 = getvalue(dsc.general_freq1)[0]
    elif fmt == 'BRUKERDSC':
        for key in ('MWFQ', 'MF'):
            if key in dsc:
                try:
                    ax.freq1 = float(dsc[key])
                except ValueError:
                    pass
        if 'SFOR' in dsc:
            ax.formula = dsc.SFOR
        if 'CenterField' in dsc:
            digits = ''.join(c for c in dsc.CenterField if c.isdigit() or c in '.E')
            try:
                ax.cf = float(digits) * 1e-4
            except ValueError:
                pass
        ax.title = dsc.get('TITL') or dsc.get('JCO') or '?'
        ax.sample = dsc.get('SAMP', '')
        ax.comment = dsc.get('CMNT', '')
    return ax
