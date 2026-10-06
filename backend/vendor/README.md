# Vendored code

`onmt/` is a trimmed copy of [OpenNMT-py 2.2.0](https://github.com/OpenNMT/OpenNMT-py)
(MIT licence, see `onmt/LICENSE.md`). MolScribe and RxnScribe import a few of its
modules (decoder, attention, position-wise FFN); the full package pins
`torchtext==0.5.0`, which no longer installs on current Python, so only the
needed modules are kept here. Package `__init__` files were emptied so that
importing them does not pull in torchtext. No other changes.
