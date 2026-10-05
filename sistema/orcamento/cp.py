"""Otimizador CP-SAT (OR-Tools), carregado de forma que o sistema abra mesmo quando o pandas não pode ser carregado.

O OR-Tools importa o pandas ao iniciar, só para funções auxiliares (séries de variáveis) que este sistema não usa. Em 01/10/2026 o
Windows (política de Controle de Aplicativo) passou a bloquear uma biblioteca do pandas neste computador, e o sistema inteiro deixava
de abrir. Se o pandas não carregar, entra um substituto mínimo só com os nomes que o OR-Tools consulta; o otimizador funciona igual.
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

from ortools.sat.python import cp_model  # noqa: E402,F401
