from pdm.models.specifiers import PySpecSet

p = PySpecSet('>=2.7,!=3.0.*') & PySpecSet('!=3.1.*')
print(p)
