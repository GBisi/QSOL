# QSOL TODO

## Static Domain Kernel Refactor

- [ ] MUST: Refactor `set` declarations behind the same primitive static-domain abstraction used by structure domains while preserving the existing surface syntax.
- [ ] MUST: Refactor `relation` declarations behind the same primitive tuple-domain abstraction used by structure domains while preserving membership calls and tuple binders.
- [ ] MUST: Keep diagnostics source-oriented: errors should still refer to `set`, `relation`, or `structure` surface declarations rather than leaking internal kernel names.
- [ ] MUST: Preserve grounding order and reproducibility for set, relation, and structure domains.
- [ ] NICE: Add an internal `DomainRef`/domain registry API so parser, sema, grounder, estimator, and backend code no longer special-case sets versus relations.
- [ ] NICE: Emit richer estimate output showing primitive-domain provenance after the refactor.
- [ ] NICE: Consider a later public `domain` concept only after the internal abstraction proves stable.
