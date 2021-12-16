from blinker import NamedSignal, Namespace

pdm_signals = Namespace()

post_init: NamedSignal = pdm_signals.signal("post_init")
pre_lock: NamedSignal = pdm_signals.signal("pre_lock")
post_lock: NamedSignal = pdm_signals.signal("post_lock")
pre_install: NamedSignal = pdm_signals.signal("pre_install")
post_install: NamedSignal = pdm_signals.signal("post_install")
