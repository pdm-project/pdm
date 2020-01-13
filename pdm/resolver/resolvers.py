from resolvelib import Resolver as BaseResolver
from resolvelib.resolvers import Criterion
from resolvelib.resolvers import Resolution as BaseResolution


class Resolution(BaseResolution):
    def _contribute_to_criteria(self, name, requirement, parent):
        if name is None or name not in self._criteria:
            crit = Criterion.from_requirement(self._p, requirement, parent)
            name = self._p.identify(requirement)
        else:
            crit = self._criteria[name].merged_with(self._p, requirement, parent)
        self._criteria[name] = crit


class Resolver(BaseResolver):
    resolution_class = Resolution

    def resolve(self, requirements, max_rounds=20):
        resolution = self.resolution_class(self.provider, self.reporter)
        resolution.resolve(requirements, max_rounds=max_rounds)
        return resolution.state
