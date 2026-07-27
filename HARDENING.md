# Hardening Status

Implemented:

- pre-inference input enforcement;
- pinned upstream model revisions and exact filenames;
- local weight hashing and inventory locks;
- output validation;
- atomic artifact replacement;
- prompt, contract, output, record, and source-commit evidence;
- explicit separation of fixture and weight-backed evidence;
- multi-version Python CI;
- no model weights, secrets, environments, or generated receipts committed to Git.

Pending:

- signed receipts;
- external WORM anchoring;
- dependency lock and SBOM;
- target-machine GPU CI;
- independent adversarial and semantic-equivalence evaluation;
- source-code license selection.
