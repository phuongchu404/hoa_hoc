# Test images

The PNG files used by the end-to-end tests are **not in the repository** (they are
taken from publications and private documents). Put them here to run those tests:

- `reaction_scheme.png`, `multistep_scheme.png`
- `docx2007/image1.png` … `docx2007/image29.png` — expected structures are in
  `docx2007/expected.json`

Tests whose image is missing are skipped automatically; the fast unit tests
(`pytest -m "not slow"`) need no images.
