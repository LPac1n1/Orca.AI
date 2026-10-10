"""Otimizador CP-SAT (OR-Tools), carregado de forma que o sistema abra mesmo quando o Windows bloqueia as bibliotecas dele.

O OR-Tools importa o pandas ao iniciar, só para funções auxiliares (séries de variáveis) que este sistema não usa. Em 01/10/2026 o
Windows (política de Controle de Aplicativo) passou a bloquear uma biblioteca do pandas neste computador, e o sistema inteiro deixava
de abrir. Se o pandas não carregar, entra um substituto mínimo só com os nomes que o OR-Tools consulta; o otimizador funciona igual.

Em 09/10/2026 o mesmo controle do Windows bloqueou as bibliotecas do PRÓPRIO OR-Tools (ortools.dll e libscip.dll): de novo o sistema
inteiro deixou de abrir. Agora, se o OR-Tools não carregar, `cp_model` fica None e quem otimiza são os otimizadores próprios do sistema, em
Python puro (produtos/teto.py e otimizador.py): as mesmas regras, sem depender de biblioteca compilada. `MOTIVO` diz por que ele não carregou.
Nenhuma configuração do Windows é alterada."""
import sys
import types

try:
    import pandas  # noqa: F401
except Exception:   # ImportError (DLL bloqueada) ou AttributeError (importação pela metade)
    for k in [k for k in sys.modules if k == 'pandas' or k.startswith('pandas.')]:
        del sys.modules[k]
    _pd = types.ModuleType('pandas')
    _pd.__doc__ = 'substituto mínimo do pandas (o original foi bloqueado pelo Windows); só para o OR-Tools carregar'
    for _n in ('Index', 'Series', 'DataFrame'):
        setattr(_pd, _n, type(_n, (), {}))
    sys.modules['pandas'] = _pd

MOTIVO = None
try:
    from ortools.sat.python import cp_model  # noqa: E402,F401
except Exception as _e:   # OSError (DLL bloqueada pelo Windows) ou ImportError (biblioteca ausente)
    cp_model = None
    MOTIVO = f'{type(_e).__name__}: {_e}'
    for k in [k for k in sys.modules if k == 'ortools' or k.startswith('ortools.')]:
        del sys.modules[k]


def disponivel():
    """O OR-Tools carregou? Se não, valem os otimizadores próprios do sistema."""
    return cp_model is not None
