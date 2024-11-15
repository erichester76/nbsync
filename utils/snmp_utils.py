
from pysnmp.smi import builder, view

def load_mibs(mib_list):
    mib_builder = builder.MibBuilder()
    for mib in mib_list:
        mib_builder.loadModules(mib)
    mib_view = view.MibViewController(mib_builder)
    return mib_view
